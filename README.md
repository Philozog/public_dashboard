# AP Terminal — Risk Management

A free portfolio dashboard that runs on your own computer. Record your stocks,
then see your performance against the S&P 500, risk and correlations,
Monte Carlo projections and news about the companies you own.

**Your data stays private.** Everything you enter is saved in a file on your
own computer (`data/portfolio.db`). Nothing is uploaded anywhere.

## Getting started

### 1. Install Python (once)

Download **Python 3.11 or newer** from [python.org/downloads](https://www.python.org/downloads/).
On Windows, tick **"Add python.exe to PATH"** on the first installer screen.
(On Windows the launcher below offers to install Python for you if it's missing.)

### 2. Download the dashboard

On this GitHub page, click the green **Code** button → **Download ZIP**, then
unzip it somewhere short like `C:\APTerminal` or your Documents folder.

### 3. Double-click to start

| Your computer | Double-click |
| --- | --- |
| Windows | `start-windows.bat` |
| Mac | `start-mac.command` |
| Linux | `start-linux.sh` (or run `./start-linux.sh` in a terminal) |

The first time, it sets everything up by itself (a few minutes). After that it
starts in seconds. The dashboard opens in your browser at
**http://127.0.0.1:8050**. Keep the black window open while you use it; close
it to stop.

> **Windows "Windows protected your PC" message:** click **More info → Run anyway**.
> **Mac "cannot be opened" message:** right-click `start-mac.command` → **Open** → **Open**
> (only needed the first time).

### 4. Turn on news (optional)

Everything except the news sections works without this.

1. Get a free API key at [newsapi.org](https://newsapi.org/register).
2. In the dashboard folder, copy `.env.example` and rename the copy to `.env`.
3. Open `.env` in a text editor and replace `your_newsapi_key_here` with your key.
4. Restart the dashboard.

Never share your `.env` file. It contains your personal key.

## Your first portfolio

The dashboard starts empty. To add your holdings:

1. Go to **Portfolio** → **Manage holdings**.
2. Enter a ticker (for example `AAPL`), the number of shares and the price you
   paid, pick a **Holding type** (Core, High Conviction or Moonshot) and click
   **Record Buy**.
3. Repeat for each stock. Prices update automatically while the app is running.

Analytics, Correlations and Monte Carlo fill in as soon as you have holdings.
Adjust allocation targets and the risk-free rate under **Parameters**.

## Put it on a website (optional)

To open your dashboard from any device, host it on [Render](https://render.com):

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Philozog/public_dashboard)

1. Click the button and sign in to Render (GitHub sign-in works).
2. When asked, fill in **DASHBOARD_USERS** with your name and a password,
   like `yourname:a-long-password` (see the next section), and optionally
   your **NEWS_API_KEY**.
3. Click **Apply**. After a few minutes Render gives you a link like
   `https://apothicaire-xxxx.onrender.com`. Open it and sign in with your
   name and password.

The setup uses Render's **Starter plan (about $7/month)** because it includes a
disk that keeps your portfolio saved. The free plan has no such disk and would
erase your portfolio whenever the app restarts. The online copy is separate
from the one on your computer; they don't sync.

### Give friends and family their own account

Each person signs in with their own name and password and has a **separate
portfolio**. Nobody can see anyone else's holdings.

1. In Render, open your service → **Environment**.
2. Edit **DASHBOARD_USERS** and list everyone as `name:password`, separated
   by commas:

   ```
   alex:my-long-password, sam:another-long-password, mom:third-password
   ```

   - Put **yourself first**: the first name keeps the portfolio that's
     already on the site.
   - Each name is one lowercase word (letters, numbers, `-` or `_`, no spaces),
     like `maria`; that is what the person types to sign in. Passwords need at
     least 8 characters and can't contain a comma.
3. Click **Save Changes**. The site restarts in about a minute.
4. Send each person the link plus their own name and password, privately.

To remove someone, delete their entry and save; they're signed out at once
and their portfolio stays stored in case you add them back. **Log out** is
at the top of every page. After 5 wrong passwords, that device must wait
15 minutes. You (the Render account owner) can see everyone's passwords in
Render, so tell people not to reuse a password from elsewhere.

## Updating, backups and troubleshooting

- **Update to the latest version:** download the new ZIP and copy your old
  `data` folder (and `.env`) into it, or run `git pull` if you use Git. The
  launcher installs any new packages automatically. Your portfolio is never overwritten by an update.
- **Back up your portfolio:** use **Parameters**, or copy the `data` folder.
- **Error saying the address or port 8050 is already in use:** the dashboard
  is already running in another window. Use that one, or close it first.
- **Setup failed halfway:** delete the `.venv` folder and double-click the
  launcher again.
- **No news appears:** check that `.env` exists (not `.env.example`) and contains
  your key, then restart. The free NewsAPI plan has a daily request limit.

## Disclaimer

The full disclosures are on the **Disclosures** page of the app.
For personal education and record-keeping only. Not financial advice.
Projections and statistics are based on historical data and do not predict
future results. Market data comes from Yahoo Finance via `yfinance` and may be
delayed or incomplete.

---

# For developers

Manual setup instead of the launchers: `python -m venv .venv`, install
`requirements.txt` into it, then run `main.py`. Set `DASH_DEBUG=1` for Dash dev
tools and auto-reload.

Sentiment uses a clearly labeled keyword fallback unless the optional model
dependencies are installed; see [sentiment setup](docs/sentiment.md).

## Pages

- **Portfolio:** account value, holdings, realized/unrealized P&L; validated
  fractional buy/sell records; independent category edits;
  searchable tables; quote timestamps; transaction history and allocation.
- **Analytics:** historical model of today's allocation, alpha, beta, Sharpe,
  Sortino and drawdown; separate account returns recorded since opening.
- **Correlations:** common-history correlations, volatility, diversification,
  contributions to portfolio risk and hypothetical shocks.
- **Monte Carlo:** daily-rebalanced simulations with validated covariance and
  bounded memory use; covered holdings and actual history dates are disclosed.
- **News / News Sentiment:** company-aware headlines and per-result scoring
  provenance, with invested-value coverage.
- **Parameters:** allocation targets, concentration limit, drift tolerance,
  risk-free assumption and consistent database backups.

History and benchmark controls are shared across analytical pages. Monte Carlo
uses the history setting; its expected-return assumption is separately disclosed.

## Data and migration

Live data resides in `data/portfolio.db` by default. Set `APOTHICAIRE_DB` to use a
different persistent location. Startup copies and backs up an existing legacy
root-level `portfolio.db`; it preserves original rows and records opening
balances rather than inventing past transactions. Operational databases and
backups are excluded from source control.

Cash is not tracked: account value is the market value of the holdings, and
buys and sales are treated as money added to or taken out of the account, so
they don't count as returns. Sells require an execution price and cannot
exceed existing shares. Trades and account valuations are committed atomically. Quote downloads
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

`render.yaml` describes the Render deployment (gunicorn, one worker, a
persistent disk for SQLite, and per-person sign-in from `DASHBOARD_USERS`;
see `Services/accounts.py`).
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
