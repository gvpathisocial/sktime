import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Create data folder if not exists
data_folder = './InSearch/data'
os.makedirs(data_folder, exist_ok=True)

# Symbols file (assume text file with one symbol per line, e.g., '^NSEI' or 'RELIANCE.NS')
symbols_file = './InSearch/symbols.inf'

# Load symbols from symbols.inf
if not os.path.exists(symbols_file):
    raise FileNotFoundError(f"{symbols_file} not found. Create it with one symbol per line (e.g., '^NSEI').")

with open(symbols_file, 'r') as f:
    symbols = [line.strip() for line in f if line.strip()]

# Get existing CSV files in data folder
existing_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]
existing_symbols = [f.replace('.csv', '').replace('_', '.') for f in existing_files]

# Identify new symbols (in symbols.inf but no CSV yet)
new_symbols = [s for s in symbols if s not in existing_symbols]

# Full history start date for new symbols (adjust as needed)
full_start_date = '2010-01-01'  # Earliest reasonable date for NSE data

# End date: Today (yfinance will handle non-trading days)
end_date = datetime.now().strftime('%Y-%m-%d')

# Download full data for new symbols
for symbol in new_symbols:
    try:
        data = yf.download(symbol, start=full_start_date, end=end_date)
        if not data.empty:
            file_path = os.path.join(data_folder, f'{symbol.replace(".", "_")}.csv')
            # Save with explicit Date column to avoid index issues later
            data_reset = data.reset_index().rename(columns={'index': 'Date'})
            data_reset.to_csv(file_path, index=False)
            print(f'Full data saved for new symbol {symbol} to {file_path}')
        else:
            print(f'No data available for new symbol {symbol}')
    except Exception as e:
        print(f'Error downloading full data for {symbol}: {e}')

# Incremental update for existing symbols (append missing data since last date)
for file in existing_files:
    symbol = file.replace('.csv', '').replace('_', '.')
    file_path = os.path.join(data_folder, file)
    
    try:
        # Load existing data to find last date. Read robustly and clean if necessary.
        existing_data = pd.read_csv(file_path)

        # Remove common metadata rows if present
        if len(existing_data) > 0:
            first_col = existing_data.columns[0]
            existing_data = existing_data[~existing_data[first_col].isin(['Ticker', 'Date'])].reset_index(drop=True)

        # Standardize column names
        existing_data.columns = [c.strip() for c in existing_data.columns]

        # Detect date column and convert
        date_col = None
        for col in existing_data.columns:
            if col.lower() in ['date', 'datetime', 'time', 'timestamp']:
                date_col = col
                break
        if date_col is None:
            # Try parsing any column as date; pick one with >50% parseable
            for col in existing_data.columns:
                try:
                    parsed = pd.to_datetime(existing_data[col], errors='coerce')
                    if parsed.notna().sum() / len(parsed) > 0.5:
                        date_col = col
                        break
                except Exception:
                    continue

        if date_col is None:
            print(f"Error updating {symbol}: no date column found in {file_path}")
            continue

        existing_data = existing_data.rename(columns={date_col: 'Date'})
        existing_data['Date'] = pd.to_datetime(existing_data['Date'], errors='coerce')
        existing_data = existing_data.dropna(subset=['Date'])
        if existing_data.empty:
            print(f"Error updating {symbol}: no valid rows after cleaning {file_path}")
            continue

        # Ensure OHLCV present
        cols_lower = [c.lower() for c in existing_data.columns]
        req = {'open', 'high', 'low', 'close', 'volume'}
        if not req.issubset(set(cols_lower)):
            # try common names
            print(f"Error updating {symbol}: missing OHLCV columns in {file_path}")
            continue

        last_date = existing_data['Date'].max()
        incremental_start = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')

        # Download only new data
        new_data = yf.download(symbol, start=incremental_start, end=end_date)
        if not new_data.empty:
            # Normalize new_data and append without header
            new_data_reset = new_data.reset_index().rename(columns={'index': 'Date'})
            # Keep standard OHLCV order and Date
            cols_keep = [c for c in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'] if c in new_data_reset.columns]
            new_data_to_write = new_data_reset[cols_keep]
            new_data_to_write.to_csv(file_path, mode='a', header=False, index=False)
            print(f'Appended new data for {symbol} from {incremental_start} to {end_date}')
        else:
            print(f'No new data for {symbol} (up to date)')
    except Exception as e:
        print(f'Error updating {symbol}: {e}')