import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.api as sm
from datetime import datetime, timedelta
import os

sns.set()

# --------------------------------------
# 1. SETTINGS
# --------------------------------------
stocks = ["BKT.MC", "ENG.MC", "ANA.MC", "COL.MC", "LOG.MC"]
index_ticker = "^IBEX"

end_date = datetime.today()
start_date = end_date - timedelta(days=5*365)

# Create folders
os.makedirs("figures", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# --------------------------------------
# 2. DOWNLOAD PRICE DATA
# --------------------------------------
print("Downloading price data...")
all_tickers = stocks + [index_ticker]

data = yf.download(
    tickers=all_tickers,
    start=start_date,
    end=end_date,
    auto_adjust=True
)

prices = data["Close"].dropna()
print("Prices downloaded.\n")

# --------------------------------------
# 3. MONTHLY RETURNS (ALIGN TO MONTH START)
# --------------------------------------
print("Converting to monthly returns...")

monthly_prices = prices.resample("M").last()
monthly_returns = monthly_prices.pct_change().dropna()

# Convert month-end → month-start
monthly_returns.index = monthly_returns.index.to_period("M").to_timestamp()

print("Monthly returns generated.\n")

# --------------------------------------
# 4. LOAD & CLEAN FAMA-FRENCH EUROPE FACTORS
# --------------------------------------
print("Loading Fama-French European 3 Factors...")

ff = pd.read_csv("data/Europe_3_Factors.csv", skiprows=6)

ff.rename(columns={ff.columns[0]: "Date"}, inplace=True)
ff["Date"] = ff["Date"].astype(str).str.strip()

# Keep only YYYYMM rows
ff = ff[ff["Date"].str.match(r'^\d{6}$')]
ff["Date"] = pd.to_datetime(ff["Date"], format="%Y%m")

# Convert FF dates to month-start
ff.index = ff["Date"].dt.to_period("M").dt.to_timestamp()
ff = ff.drop(columns=["Date"])

# Keep only factor columns
ff = ff[["Mkt-RF", "SMB", "HML", "RF"]]

# Convert numeric
for col in ff.columns:
    ff[col] = pd.to_numeric(ff[col], errors="coerce")

ff = ff.dropna()
ff = ff / 100.0   # percent → decimal

print("FF dates:", ff.index.min(), "→", ff.index.max(), "\n")

# --------------------------------------
# 5. CREATE STOCK + INDEX RETURNS BEFORE MERGING
# --------------------------------------
stock_returns = monthly_returns[stocks]
index_returns = monthly_returns[index_ticker]

# Align to FF date range
stock_returns = stock_returns.loc[ff.index.min(): ff.index.max()]
index_returns = index_returns.loc[ff.index.min(): ff.index.max()]

print("Stock returns shape:", stock_returns.shape)
print("Index returns shape:", index_returns.shape, "\n")

# --------------------------------------
# 6. MERGE RETURNS + FACTORS
# --------------------------------------
print("Merging data...")

data_merged = pd.concat(
    [stock_returns, index_returns.rename("IBEX"), ff],
    axis=1
).dropna()

print("Data merged:", data_merged.shape, "\n")

# Compute excess returns
excess_stock_returns = data_merged[stocks].sub(data_merged["RF"], axis=0)
excess_ibex = data_merged["IBEX"] - data_merged["RF"]
SMB = data_merged["SMB"]
HML = data_merged["HML"]

# --------------------------------------
# 7. FILTER ONLY VALID STOCKS
# --------------------------------------
valid_stocks = [s for s in stocks if not excess_stock_returns[s].dropna().empty]
print("Valid stocks:", valid_stocks, "\n")

excess_stock_returns = excess_stock_returns[valid_stocks]
stock_returns = stock_returns[valid_stocks]

# --------------------------------------
# 8. CAPM REGRESSION
# --------------------------------------
print("Running CAPM regressions...")
capm_results = []

for s in valid_stocks:
    y = excess_stock_returns[s]

    # Create X with correct column names
    X = pd.DataFrame({
        "const": 1,
        "IBEX": excess_ibex
    })

    model = sm.OLS(y, X).fit()

    capm_results.append({
        "Stock": s,
        "Alpha": model.params["const"],
        "Beta_IBEX": model.params["IBEX"],
        "Alpha_t": model.tvalues["const"],
        "Beta_t": model.tvalues["IBEX"],
        "R2": model.rsquared
    })

capm_df = pd.DataFrame(capm_results)
capm_df.to_excel("outputs/CAPM_results_244604.xlsx", index=False)
print("CAPM results saved.\n")

# --------------------------------------
# 9. FAMA-FRENCH 3-FACTOR REGRESSION
# --------------------------------------
print("Running Fama-French regressions...")
ff_results = []

for s in valid_stocks:
    y = excess_stock_returns[s]

    X = pd.concat([
        excess_ibex.rename("EX_IBEX"),
        SMB.rename("SMB"),
        HML.rename("HML")
    ], axis=1)

    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()

    ff_results.append({
        "Stock": s,
        "Alpha": model.params["const"],
        "Beta_IBEX": model.params["EX_IBEX"],
        "SMB_coef": model.params["SMB"],
        "HML_coef": model.params["HML"],
        "R2": model.rsquared
    })

ff_df = pd.DataFrame(ff_results)
ff_df.to_excel("outputs/FF3_results_244604.xlsx", index=False)
print("Fama-French results saved.\n")

# --------------------------------------
# 10. PRICE DEVELOPMENT PLOT
# --------------------------------------
print("Generating price plot...")
plt.figure(figsize=(10, 6))

for s in valid_stocks:
    plt.plot(prices.index, prices[s], label=s)

plt.title("Price Development of Assigned Stocks (Last 5 Years)")
plt.xlabel("Date")
plt.ylabel("Adjusted Price")
plt.legend()
plt.tight_layout()
plt.savefig("figures/price_development_244604.png", dpi=300)
plt.close()
print("Price plot saved.\n")

# --------------------------------------
# 11. JOINTPLOTS
# --------------------------------------
print("Generating jointplots...")
for s in valid_stocks:
    tmp = pd.DataFrame({
        s: stock_returns[s],
        "IBEX": index_returns
    }).dropna()

    g = sns.jointplot(
        data=tmp,
        x="IBEX",
        y=s,
        kind="reg"
    )

    g.fig.suptitle(f"Jointplot of {s} vs IBEX Monthly Returns")
    g.fig.tight_layout()
    g.fig.subplots_adjust(top=0.95)

    g.fig.savefig(f"figures/jointplot_{s}_244604.png", dpi=300)
    plt.close(g.fig)

print("All jointplots saved.\n")

print("Assignment completed successfully!")
