import duckdb
from pathlib import Path
import os
from tqdm import tqdm
import signal
import sys
import time
import shutil

RAW_DATA_DIR = "options-data"
CONSOLIDATED_DATA_DIR = "consolidated-data-by-symbol"
CONSOLIDATED_DATA_DIR_B = f"{CONSOLIDATED_DATA_DIR}_B"  # New directory for second consolidation

os.makedirs(f"{CONSOLIDATED_DATA_DIR}", exist_ok=True)

con = duckdb.connect()

# Create view over Hive-style partitioned parquet
con.execute(f"""
CREATE OR REPLACE VIEW RAW_OPTIONS_DATA AS
SELECT *
FROM read_parquet('{RAW_DATA_DIR}/*/*.parquet', hive_partitioning=1);
""")

# Fetch all unique dt values
dt_list = [row[0] for row in con.execute("SELECT DISTINCT dt FROM RAW_OPTIONS_DATA ORDER BY 1").fetchall()]

print(f"Found {len(dt_list)} dates to process.")

parquet_files = list(Path(CONSOLIDATED_DATA_DIR).rglob("*.parquet"))

# Skip dt if already exists
if parquet_files:
    existing_dt_list = con.execute(f"""
        SELECT DISTINCT dt
        FROM read_parquet('{CONSOLIDATED_DATA_DIR}/**/*.parquet', hive_partitioning=1)
        """).fetchall()
    existing_dt_list = [row[0] for row in existing_dt_list]
else:
    existing_dt_list = []

# --- Graceful cancellation handling ---
stop_requested = False

def swap_directories(dir_a: str, dir_b: str):
    a = Path(dir_a)
    b = Path(dir_b)
    tmp = a.parent / f"__swap_tmp_{a.name}"

    # Swap directories
    a.rename(tmp)   # dir_a -> temp
    b.rename(a)     # dir_b -> dir_a
    tmp.rename(b)   # temp -> dir_b

    pbar.write(f"Swapped '{dir_a}' <-> '{dir_b}'")

def data_exists_for_dt(dt: str) -> bool:
    """Check if at least one parquet file exists for given dt in any symbol partition."""
    pattern = f"symbol=*/dt={dt}/*.parquet"
    return any(Path(CONSOLIDATED_DATA_DIR).glob(pattern))

def handle_sigint(sig, frame):
    global stop_requested
    pbar.write("Cancellation requested... will finish current dt and then stop.")
    stop_requested = True

signal.signal(signal.SIGINT, handle_sigint)
# -------------------------------------

### Step 1: Consolidate by symbol and dt into partitioned parquet files ###
# tqdm progress bar
with tqdm(dt_list, desc="Processing Dates", unit="day") as pbar:
    for i, dt in enumerate(dt_list, start=1):        
        if stop_requested:
            pbar.write("Stopping before starting next dt.")
            break

        pbar.set_postfix_str(f"dt={dt}")
        pbar.refresh()

        try:
            parquet_files = list(Path(CONSOLIDATED_DATA_DIR).rglob("*.parquet"))

            # Skip dt if already exists
            if dt in existing_dt_list:
                # dt1 = con.execute(f"""
                #     SELECT dt
                #     FROM read_parquet('{CONSOLIDATED_DATA_DIR}/**/*.parquet', hive_partitioning=1)
                #     WHERE dt = '{dt}'
                #     LIMIT 1
                #     """).fetchall()
                # if len(dt1) > 0:
                pbar.write(f"Skipping dt={dt}, already exists.")
                pbar.update()
                continue
            # if data_exists_for_dt(dt):
            #     pbar.write(f"Skipping dt={dt}, already exists.")
            #     pbar.n += 1
            #     pbar.refresh()
            #     continue

            # ---- Timed Section ----
            start_time = time.perf_counter()
            
            # Main consolidation query
            con.execute(f"""
                COPY (
                    SELECT dt, symbol, option, option_symbol, option_type,
                        CAST(strike AS FLOAT)/1000 AS strike,
                        CAST(strptime('20'|| expiration, '%Y%m%d') AS DATE) AS expiration,
                        open_interest, volume, delta, gamma, vega, theta, rho, theo, open, high, iv, bid, ask
                    FROM (
                        SELECT dt,
                               REPLACE(symbol,'_', '') AS symbol,
                               option,
                               UNNEST(
                                   regexp_extract(
                                       option,
                                       '(\\w+)(\\d{{6}})([CP])(\\d+)',
                                       ['option_symbol', 'expiration', 'option_type', 'strike']
                                   )
                               ),
                               open_interest, volume, delta, gamma, vega, theta, rho, theo, open, high, iv, bid, ask
                        FROM RAW_OPTIONS_DATA
                        WHERE dt = '{dt}'
                    ) T                    
                ) TO '{CONSOLIDATED_DATA_DIR}'
                (FORMAT PARQUET, PARTITION_BY (symbol), APPEND TRUE);
                --(FORMAT PARQUET, PARTITION_BY (symbol), OVERWRITE TRUE);
            """)
            
            pbar.write(f"Consolidated dt={dt} in {time.perf_counter() - start_time:,.2f} seconds.")

        except Exception as e:
            pbar.write(f"Error processing dt={dt}: {e}")
            continue
        
        pbar.update()

### Step:2 Final consolidation by symbol into single parquet files ###

if os.path.exists(CONSOLIDATED_DATA_DIR_B) and os.path.isdir(CONSOLIDATED_DATA_DIR_B):
    shutil.rmtree(CONSOLIDATED_DATA_DIR_B)

os.makedirs(CONSOLIDATED_DATA_DIR_B, exist_ok=True)

symbol_dirs = [d for d in Path(CONSOLIDATED_DATA_DIR).iterdir() if d.is_dir()]

for symbol_dir in tqdm(symbol_dirs, desc="Consolidating symbols", unit="symbol"):
    if stop_requested:
        tqdm.write("Stopping before starting next dt.")
        break
    symbol = symbol_dir.name    
    # Create output subfolder (e.g., consolidated-data-merged/AAPL/)
    output_symbol_dir = Path(CONSOLIDATED_DATA_DIR_B) / symbol
    output_symbol_dir.mkdir(parents=True, exist_ok=True)
    
    parquet_pattern = f"{symbol_dir}/*.parquet"
    output_file = output_symbol_dir / "data.parquet"

    # Consolidate all parquet files for the symbol
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{parquet_pattern}')
            ORDER BY dt
        ) TO '{output_file}' (FORMAT PARQUET);
    """)

    tqdm.write(f"Consolidated {symbol} -> {output_file}")

if not stop_requested:
    # Swap directories
    swap_directories(CONSOLIDATED_DATA_DIR, CONSOLIDATED_DATA_DIR_B)

pbar.close()
if stop_requested:
    pbar.write("Process was cancelled by user.")
else:
    pbar.write("Done (or cancelled gracefully).")
