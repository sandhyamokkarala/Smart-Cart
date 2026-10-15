from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

from app.database import MODEL_DIR


FEATURES = [
    "customer_age", "total_purchases", "total_spending", "average_order_value",
    "website_visits", "product_price", "product_rating", "product_views",
    "cart_additions", "wishlist_additions", "previous_purchases", "time_spent",
]
SEGMENT_FEATURES = ["total_purchases", "total_spending", "average_order_value", "website_visits", "purchase_frequency"]
PURCHASE_MODEL_PATH = MODEL_DIR / "purchase_model.pkl"
SEGMENT_MODEL_PATH = MODEL_DIR / "customer_segment_model.pkl"


def train_models(activity: pd.DataFrame, customers: pd.DataFrame) -> dict:
    data = activity[FEATURES + ["purchased"]].copy()
    x_train, x_test, y_train, y_test = train_test_split(
        data[FEATURES], data["purchased"], test_size=0.25, random_state=42, stratify=data["purchased"]
    )
    candidates = {
        "Logistic Regression": LogisticRegression(max_iter=1200, class_weight="balanced", random_state=42),
        "Decision Tree": DecisionTreeClassifier(max_depth=8, min_samples_leaf=8, class_weight="balanced", random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=180, min_samples_leaf=3, class_weight="balanced_subsample", random_state=42, n_jobs=-1),
    }
    results = {}
    best_name = ""
    best_auc = -1.0
    for name, estimator in candidates.items():
        pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", estimator)])
        pipeline.fit(x_train, y_train)
        probabilities = pipeline.predict_proba(x_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        auc = float(roc_auc_score(y_test, probabilities))
        results[name] = {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "precision": round(float(precision_score(y_test, predictions, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, predictions, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, predictions, zero_division=0)), 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        }
        if auc > best_auc:
            best_name, best_auc = name, auc
    selected = candidates[best_name]
    final_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", selected)])
    final_pipeline.fit(data[FEATURES], data["purchased"])
    joblib.dump({"pipeline": final_pipeline, "features": FEATURES, "selected_model": best_name, "metrics": results}, PURCHASE_MODEL_PATH)

    segment_data = customers.copy()
    segment_data["purchase_frequency"] = segment_data["total_purchases"] / 12
    segment_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", KMeans(n_clusters=4, n_init=20, random_state=42))])
    labels = segment_pipeline.fit_predict(segment_data[SEGMENT_FEATURES])
    means = segment_data.assign(cluster=labels).groupby("cluster")["total_spending"].mean().sort_values(ascending=False)
    segment_names = {int(cluster): name for cluster, name in zip(means.index, ["Premium Customer", "Regular Customer", "Occasional Customer", "At-Risk Customer"])}
    joblib.dump({"pipeline": segment_pipeline, "features": SEGMENT_FEATURES, "segment_names": segment_names}, SEGMENT_MODEL_PATH)
    return {"models": results, "selected_model": best_name, "segments": segment_names}


def load_purchase_model() -> dict:
    if not PURCHASE_MODEL_PATH.exists():
        raise FileNotFoundError("Purchase model is not available. Run python -m app.seed first.")
    return joblib.load(PURCHASE_MODEL_PATH)


def load_segment_model() -> dict:
    if not SEGMENT_MODEL_PATH.exists():
        raise FileNotFoundError("Customer segment model is not available. Run python -m app.seed first.")
    return joblib.load(SEGMENT_MODEL_PATH)


def purchase_probability(features: dict) -> float:
    artifact = load_purchase_model()
    row = pd.DataFrame([{key: features.get(key, np.nan) for key in artifact["features"]}])
    return float(artifact["pipeline"].predict_proba(row)[0, 1])


def customer_segment(customer: dict) -> str:
    artifact = load_segment_model()
    values = dict(customer)
    values["purchase_frequency"] = values.get("total_purchases", 0) / 12
    row = pd.DataFrame([{key: values.get(key, np.nan) for key in artifact["features"]}])
    cluster = int(artifact["pipeline"].predict(row)[0])
    return artifact["segment_names"][cluster]