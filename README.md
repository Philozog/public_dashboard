# Apothicaire — Risk Management

A free portfolio dashboard that runs on your own computer. Record your stocks
and cash, then see your performance against the S&P 500, risk and correlations,
Monte Carlo projections and news about the companies you own.

**Your data stays private.** Everything you enter is saved in a file on your
own computer (`data/portfolio.db`). Nothing is uploaded anywhere.

## Getting started

You need about 10 minutes, the first time only.

### 1. Install Python

Download **Python 3.11 or newer** from [python.org/downloads](https://www.python.org/downloads/).
On Windows, tick **"Add python.exe to PATH"** on the first installer screen.

### 2. Download the dashboard

Either:
- **No Git:** on this GitHub page, click the green **Code** button →
  **Download ZIP**, then unzip it somewhere short like `C:\Apothicaire`, or
- **With Git:** `git clone https://github.com/Philozog/public_dashboard.git`

> On Windows, avoid very deep folders. Paths longer than ~260 characters
> can make the install fail with "filename or extension is too long".

### 3. Install and run

Open a terminal **inside the dashboard folder** (Windows: open the folder in
File Explorer, click the address bar, type `powershell` and press Enter).

**Windows**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Then open **http://127.0.0.1:8050** in your browser. Leave the terminal open
while you use the dashboard. Press `Ctrl+C` in it to stop.

Next time, you only need the last line (`... main.py`).

### 4. Turn on news (optional)

Everything except the news sections works without this.

1. Get a free API key at [newsapi.org](https://newsapi.org/register).
2. In the dashboard folder, copy `.env.example` and rename the copy to `.env`.
3. Open `.env` in a text editor and replace `your_newsapi_key_here` with your key.
4. Restart the dashboard.

Never share your `.env` file. It contains your personal key.

## Your first portfolio

The dashboard starts empty. To add your holdings:

1. Go to **Portfolio** → **Cash movements**, and record a **Deposit** for your
   cash. Purchases are paid from this cash, so you need to deposit before buying.
2. Under **Manage holdings**, enter a ticker (for example `AAPL`), the number of
   shares and the price you paid, pick a **Holding type** (Core, High Conviction
   or Moonshot) and click **Record Buy**.
3. Repeat for each stock. Prices update automatically while the app is running.

Analytics, Correlations and Monte Carlo fill in as soon as you have holdings.
Adjust allocation targets and the risk-free rate under **Settings**.

## Updating, backups and troubleshooting

- **Update to the latest version:** with Git, run `git pull` in the folder.
  Otherwise, download the new ZIP and copy your old `data` folder (and `.env`)
  into it. Your portfolio is never overwritten by an update.
- **Back up your portfolio:** use **Settings**, or copy the `data` folder.
- **Error saying the address or port 8050 is already in use:** the dashboard
  is already running in another terminal. Use that one, or close it first.
- **No news appears:** check that `.env` exists (not `.env.example`) and contains
  your key, then restart. The free NewsAPI plan has a daily request limit.

## Disclaimer

For personal education and record-keeping only. Not financial advice.
Projections and statistics are based on historical data and do not predict
future results. Market data comes from Yahoo Finance via `yfinance` and may be
delayed or incomplete.

---

# For developers

Sentiment uses a clearly labeled keyword fallback unless the optional model
dependencies are installed; see [sentiment setup](docs/sentiment.md).

## Pages

- **Portfolio:** account value, holdings, cash, realized/unrealized P&L; validated
  fractional buy/sell records; independent category edits; cash movements;
  searchable tables; quote timestamps; transaction history and allocation.
- **Analytics:** historical model of today's allocation, alpha, beta, Sharpe,
  Sortino and drawdown; separate account returns recorded since opening.
- **Correlations:** common-history correlations, volatility, diversification,
  contributions to portfolio risk and hypothetical shocks.
- **Monte Carlo:** daily-rebalanced simulations with validated covariance and
  bounded memory use; covered holdings and actual history dates are disclosed.
- **News / News Sentiment:** company-aware headlines and per-result scoring
  provenance, with invested-value coverage.
- **Settings:** allocation targets, concentration limit, drift tolerance,
  risk-free assumption and consistent database backups.

History and benchmark controls are shared across analytical pages. Monte Carlo
uses the history setting; its expected-return assumption is separately disclosed.

## Data and migration

Live data resides in `data/portfolio.db` by default. Set `APOTHICAIRE_DB` to use a
different persistent location. Startup copies and backs up an existing legacy
root-level `portfolio.db`; it preserves original rows and records opening
balances rather than inventing past transactions. Operational databases and
backups are excluded from source control.

Opening cash is zero until entered as a deposit. New buys require recorded cash;
sells require an execution price and cannot exceed existing shares. Trades,
cash movements and account valuations are committed atomically. Quote downloads
occur outside write transactions and never change position edit timestamps.

Read the [upgrade and calculation guide](docs/upgrade-guide.md) before relying
on the new account history. It explains migration, accounting assumptions,
coverage, quote freshness and restoration.

## Verification

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests use temporary databases and synthetic market data. CI runs the suite on
pushes and pull requests. Optional browser and lint checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check Services pages tests app.py main.py data_base.py publish.py
.\.venv\Scripts\python.exe -B tests/browser_check.py
```

The browser check uses installed Microsoft Edge in headless mode, a temporary
portfolio and offline quotes. Screenshots go to `test-results/`.

## Deployment

`app.py` exports `app` and `server` without starting a development server.
`python publish.py` prepares a clean, timestamped release under `dist/` without
publishing. It excludes secrets and private data by default; `--include-data`
explicitly includes a current SQLite snapshot. Review that directory before
using it as the Plotly Cloud project path.

Configure secrets on the host and provision durable storage for the operational
database. Bundling SQLite in a release does not guarantee persistence or sync
local and cloud edits. Keep off-machine backups. Existing Plotly app identifiers
belong in a local `plotly-cloud.toml`, which is excluded from source control
and copied into the release only when present; nothing deploys automatically.

## Structure

`pages/` contains Dash layouts and callbacks. `Services/` contains the ledger,
migrations, settings, price cache, performance calculations, quote updater,
news, sentiment and reusable UI components. `schema.sql` is the canonical
schema; `data_base.py` and the legacy cleanup entry point use safe migrations.
