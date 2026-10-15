# SmartCart

SmartCart is a runnable e-commerce demo with a FastAPI + SQLite backend, customer/admin JWT roles, synthetic CSV data, purchase prediction, K-Means segments, recommendations, analytics, and a browser storefront.

## Run locally (Windows PowerShell)

```powershell
cd SmartCart
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 for the storefront and http://127.0.0.1:8000/docs for Swagger UI. The database, generated CSV datasets, trained models, and EDA charts are created on first run.

## Deploy to Render

Push the `SmartCart` directory to a GitHub repository, then create a Blueprint in Render using its root `render.yaml`. The Blueprint provisions the FastAPI web service and PostgreSQL database and generates a JWT secret. The first service start seeds the database and trains the demo models. Render's free services are intended for demos; confirm current plan limits and database retention in your Render dashboard.

Demo accounts: `customer1@example.com` / `customer1234` and `admin@example.com` / `admin1234`. Change `JWT_SECRET` before deploying; this demo is not production-hardened.

## Libraries

FastAPI and Uvicorn serve the APIs; SQLAlchemy connects to SQLite (or a configured PostgreSQL URL); Pydantic validates requests; pandas/NumPy handle datasets; scikit-learn trains classifiers and K-Means; joblib stores model artifacts; PyJWT signs tokens; pytest/httpx test APIs; Matplotlib/Seaborn create EDA visualizations.

## Data and ML

`python -m app.seed` writes 100 customers, 50 products, 600 orders, and 5,000 customer-product activity rows to `data/`, creates the relational seed database, evaluates Logistic Regression, Decision Tree, and Random Forest, selects by ROC-AUC, saves `purchase_model.pkl` and `customer_segment_model.pkl`, and writes EDA charts under `reports/`.

Before production model training, split data by customer or time to avoid leakage; encode categorical values; impute or reject missing data; scale numeric features for distance/linear models; address class imbalance; and evaluate on held-out data. The generated interaction dataset is synthetic and demonstrates the workflow, not real purchasing behavior.

## API journey

Register/login, browse products, fetch recommendations, add cart items, place an order, then call purchase prediction, customer segment, and dashboard endpoints. Admin analytics live under `/admin/*`; the seeded admin account is required. Interactive endpoint schemas and examples are available in Swagger UI.