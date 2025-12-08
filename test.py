import yfinance as yf

tickers = ["BKT.MC", "ENG.MC", "ANA.MC", "COL.MC", "LOG.MC"]

for t in tickers:
    df = yf.download(t, period="5y", auto_adjust=True)
    print(t, "→", df.shape)