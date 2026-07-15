"""
Correction Templates for Audit and Construction Frameworks.

This module provides structured correction suggestions for each audit pass
and construction phase, including problem descriptions, bad/good code examples,
and explanations.
"""

AUDIT_CORRECTIONS = {
    1: {
        "name": "Structural Overview",
        "description": "Verify notebook has clear structure and coherent purpose",
        "corrections": [
            {
                "issue": "Missing section headers",
                "severity": "HIGH",
                "problem": "Notebook lacks markdown section headers making navigation difficult",
                "bad_example": "Code cells without any markdown explanation between them",
                "good_example": """# Environment & Dependencies
# ...cells...

## Data Ingestion
# ...cells...

### Preprocessing & Feature Engineering
# ...cells...""",
                "why_it_matters": "Section headers establish clarity and help readers understand workflow structure"
            },
            {
                "issue": "Multiple unrelated purposes",
                "severity": "CRITICAL",
                "problem": "Notebook mixes unrelated experiments or workflows",
                "bad_example": "Notebook handles both time-series forecasting AND image classification in same file",
                "good_example": "Split into separate notebooks: forecast_rnn.ipynb and image_classifier.ipynb",
                "why_it_matters": "Single-purpose notebooks are easier to maintain, debug, and reuse"
            },
            {
                "issue": "Out-of-order cell execution",
                "severity": "CRITICAL",
                "problem": "Execution counters show non-sequential numbers (e.g., [5] then [2] then [8])",
                "bad_example": "Cells executed out of sequence: [ ]: [5], [ ]: [2], [ ]: [10]",
                "good_example": "Cells executed in order: [ ]: [1], [ ]: [2], [ ]: [3]",
                "why_it_matters": "Out-of-order execution hides dependencies and breaks reproducibility"
            },
            {
                "issue": "Empty code cell outputs",
                "severity": "MEDIUM",
                "problem": "Code cells show execution counter but have no output",
                "bad_example": "[5] (no output shown below cell)",
                "good_example": "[5] (output visible or intentionally silent with pass/return)",
                "why_it_matters": "Empty outputs may indicate failed computations or missing assertions"
            }
        ]
    },
    2: {
        "name": "Reproducibility Check",
        "description": "Verify notebook can run on different machines with pinned dependencies",
        "corrections": [
            {
                "issue": "No dependency file",
                "severity": "HIGH",
                "problem": "Missing requirements.txt, environment.yml, or pyproject.toml",
                "bad_example": "Notebook imports pandas, numpy, sklearn but no dependency file exists",
                "good_example": """# requirements.txt
pandas==2.0.3
numpy==1.24.3
scikit-learn==1.3.0
matplotlib==3.7.1""",
                "why_it_matters": "Without pinned versions, users get different package versions leading to inconsistent results"
            },
            {
                "issue": "No random seed initialization",
                "severity": "HIGH",
                "problem": "Results vary on each run due to uncontrolled randomness",
                "bad_example": """# No seed set anywhere
model = RandomForestClassifier()
model.fit(X_train, y_train)""",
                "good_example": """import random
import numpy as np
import torch

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)""",
                "why_it_matters": "Fixed seeds ensure deterministic output across runs and machines"
            },
            {
                "issue": "Hardcoded absolute paths",
                "severity": "HIGH",
                "problem": "Paths like /Users/john/data.csv only work on specific machines",
                "bad_example": 'data = pd.read_csv("/Users/john/projects/data.csv")',
                "good_example": """from pathlib import Path
notebook_dir = Path.cwd()
data_path = notebook_dir / "data" / "data.csv"
data = pd.read_csv(data_path)""",
                "why_it_matters": "Relative paths work across different machines and environments"
            }
        ]
    },
    3: {
        "name": "Data Integrity Review",
        "description": "Verify train/test split happens before preprocessing to prevent leakage",
        "corrections": [
            {
                "issue": "Train/test split after preprocessing",
                "severity": "CRITICAL",
                "problem": "Data split occurs after scaling/encoding, causing leakage from test into train",
                "bad_example": """# WRONG ORDER
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)  # Fit on ALL data
X_train, X_test = train_test_split(X_scaled)""",
                "good_example": """# CORRECT ORDER
X_train, X_test = train_test_split(X)  # Split FIRST
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)  # Fit on train only
X_test_scaled = scaler.transform(X_test)  # Apply to test""",
                "why_it_matters": "Preprocessing on full data causes test data to leak into training, inflating model performance"
            },
            {
                "issue": "Missing train/test split",
                "severity": "CRITICAL",
                "problem": "Model trained and evaluated on same data",
                "bad_example": """X_train = data.iloc[:, :-1]
y_train = data.iloc[:, -1]
model.fit(X_train, y_train)
score = model.score(X_train, y_train)  # Evaluating on training data""",
                "good_example": """from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
model.fit(X_train, y_train)
score = model.score(X_test, y_test)  # Evaluate on unseen test data""",
                "why_it_matters": "Test set must be truly unseen to get honest model performance estimate"
            },
            {
                "issue": "Inconsistent missing-data handling",
                "severity": "MEDIUM",
                "problem": "Missing values handled differently on train vs test",
                "bad_example": """# Impute train and test separately
imputer_train = SimpleImputer()
X_train = imputer_train.fit_transform(X_train)
imputer_test = SimpleImputer()  # Wrong: different imputer
X_test = imputer_test.fit_transform(X_test)""",
                "good_example": """imputer = SimpleImputer()
X_train = imputer.fit_transform(X_train)  # Fit on train
X_test = imputer.transform(X_test)  # Use same statistics on test""",
                "why_it_matters": "Consistent imputation strategy ensures test data is handled the same way train data was"
            }
        ]
    },
    4: {
        "name": "ML Correctness Audit",
        "description": "Verify modeling methodology is sound (metrics, CV, tuning, baselines)",
        "corrections": [
            {
                "issue": "Accuracy on imbalanced dataset",
                "severity": "HIGH",
                "problem": "Using accuracy metric when classes are imbalanced misleads performance",
                "bad_example": """# 95% class A, 5% class B
# Model predicts all class A -> 95% accuracy but useless!
from sklearn.metrics import accuracy_score
accuracy = accuracy_score(y_test, predictions)""",
                "good_example": """from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
precision, recall, f1, _ = precision_recall_fscore_support(y_test, predictions, average='weighted')
roc_auc = roc_auc_score(y_test, predictions_proba)
print(f"F1: {f1}, ROC-AUC: {roc_auc}")""",
                "why_it_matters": "F1, precision, recall, and ROC-AUC are more informative for imbalanced classification"
            },
            {
                "issue": "No baseline comparison",
                "severity": "MEDIUM",
                "problem": "Model performance reported in isolation without context",
                "bad_example": 'print(f"Model accuracy: {accuracy}")  # Is 75% good?',
                "good_example": """from sklearn.dummy import DummyClassifier
baseline = DummyClassifier(strategy='most_frequent')
baseline.fit(X_train, y_train)
baseline_score = baseline.score(X_test, y_test)
model_score = model.score(X_test, y_test)
print(f"Baseline: {baseline_score}, Model: {model_score}")""",
                "why_it_matters": "Baseline provides context—know if 75% is better than guessing"
            },
            {
                "issue": "Hyperparameter tuning on test set",
                "severity": "CRITICAL",
                "problem": "Tuning parameters using test data causes overfitting",
                "bad_example": """# WRONG
best_param = find_best_param_on_test_set(X_test, y_test)
model = Model(param=best_param)
model.fit(X_train, y_train)
score = model.score(X_test, y_test)  # Test data was used for tuning!""",
                "good_example": """# RIGHT
X_train, X_val, y_train, y_val = train_test_split(X_train, y_train)
best_param = find_best_param_on_validation(X_val, y_val)
model = Model(param=best_param)
model.fit(X_train, y_train)
score = model.score(X_test, y_test)  # Test is truly unseen""",
                "why_it_matters": "Test set must never influence model selection or parameter tuning"
            }
        ]
    },
    5: {
        "name": "Code Quality Review",
        "description": "Verify code is maintainable, non-repetitive, and clean",
        "corrections": [
            {
                "issue": "Repeated code blocks (3+ occurrences)",
                "severity": "MEDIUM",
                "problem": "Same logic copied multiple times instead of factored into function",
                "bad_example": """# Cell 5
plt.figure(figsize=(10, 6))
plt.plot(data1)
plt.title('Series 1')
plt.xlabel('Time')
plt.ylabel('Value')
plt.show()

# Cell 10
plt.figure(figsize=(10, 6))
plt.plot(data2)
plt.title('Series 2')
plt.xlabel('Time')
plt.ylabel('Value')
plt.show()

# Cell 15 (same again)
plt.figure(figsize=(10, 6))
plt.plot(data3)
plt.title('Series 3')
plt.xlabel('Time')
plt.ylabel('Value')
plt.show()""",
                "good_example": """def plot_time_series(data, title):
    plt.figure(figsize=(10, 6))
    plt.plot(data)
    plt.title(title)
    plt.xlabel('Time')
    plt.ylabel('Value')
    plt.show()

plot_time_series(data1, 'Series 1')
plot_time_series(data2, 'Series 2')
plot_time_series(data3, 'Series 3')""",
                "why_it_matters": "DRY (Don't Repeat Yourself) principle reduces bugs and improves maintainability"
            },
            {
                "issue": "Unused imports",
                "severity": "LOW",
                "problem": "Import statements for modules never used in code",
                "bad_example": """import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
# ... but sns never used""",
                "good_example": """import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
# Only include what's actually used""",
                "why_it_matters": "Unused imports clutter code and increase dependencies unnecessarily"
            },
            {
                "issue": "Bloated cell outputs",
                "severity": "MEDIUM",
                "problem": "Entire DataFrame or tensor printed without truncation",
                "bad_example": """print(large_dataframe)  # 10,000 rows printed to screen""",
                "good_example": """print(large_dataframe.head(10))  # Show only first 10
print(f"Shape: {large_dataframe.shape}")
print(large_dataframe.info())  # Summary instead of raw output""",
                "why_it_matters": "Large outputs make notebook hard to read and slow to load"
            }
        ]
    },
    6: {
        "name": "Deployment Readiness",
        "description": "Verify notebook can be deployed, artifacts are versioned, and PII is safe",
        "corrections": [
            {
                "issue": "Models not saved with versioning",
                "severity": "HIGH",
                "problem": "Model saved as fixed filename, overwriting previous versions",
                "bad_example": """import joblib
joblib.dump(model, 'model.pkl')  # Same filename every time""",
                "good_example": """from datetime import datetime
import joblib
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
model_path = f'models/model_{timestamp}.pkl'
joblib.dump(model, model_path)
print(f'Saved to {model_path}')""",
                "why_it_matters": "Versioning allows tracking model history and rolling back if needed"
            },
            {
                "issue": "Inference entangled with training",
                "severity": "MEDIUM",
                "problem": "Model loading requires running entire training pipeline",
                "bad_example": """# To use model, must run all training cells
# No way to just load and predict""",
                "good_example": """# inference.py - separate file
import joblib
model = joblib.load('models/model_20250115_143022.pkl')
predictions = model.predict(new_data)

# notebook.ipynb - just saves model
joblib.dump(model, f'models/model_{timestamp}.pkl')""",
                "why_it_matters": "Separable inference allows deployment without training code"
            },
            {
                "issue": "No resource documentation",
                "severity": "MEDIUM",
                "problem": "No record of compute/memory requirements",
                "bad_example": "Notebook runs but users don't know if GPU is needed",
                "good_example": """# Runtime: ~5 minutes on CPU
# Memory: ~2GB peak usage
# GPU: Optional (speeds up by 3x if available)
# Dependencies: See requirements.txt""",
                "why_it_matters": "Resource docs help users choose appropriate hardware"
            },
            {
                "issue": "PII or credentials in notebook",
                "severity": "CRITICAL",
                "problem": "Passwords, API keys, or personal data visible in cells",
                "bad_example": 'api_key = "sk_live_abc123def456"  # Hardcoded!',
                "good_example": """import os
api_key = os.environ.get('API_KEY')
assert api_key, 'Set API_KEY environment variable'""",
                "why_it_matters": "Credentials in version control are a security breach"
            }
        ]
    }
}

CONSTRUCTION_CORRECTIONS = {
    1: {
        "name": "Scaffold (Phase 1)",
        "description": "Set up notebook structure before writing any logic",
        "corrections": [
            {
                "issue": "Missing section headers",
                "severity": "HIGH",
                "problem": "Notebook lacks standard section organization",
                "bad_example": "Just code cells with no markdown structure",
                "good_example": """# Environment & Dependencies
# Configuration & Global Parameters
# Data Ingestion
# Preprocessing & Feature Engineering
# Model Definition & Training
# Evaluation & Metrics
# Artifact Export
# Conclusions & Next Steps""",
                "why_it_matters": "Standard headers create consistent, navigable structure across all notebooks"
            },
            {
                "issue": "No dependency pinning at start",
                "severity": "HIGH",
                "problem": "Environment setup comes after code, or versions not pinned",
                "bad_example": "!pip install pandas numpy sklearn at cell 15",
                "good_example": """# Cell 1: Create requirements.txt with pinned versions
# Then: !pip install -r requirements.txt""",
                "why_it_matters": "Reproducible environment from the start prevents version conflicts"
            },
            {
                "issue": "Missing random seed initialization",
                "severity": "MEDIUM",
                "problem": "Reproducibility controls deferred or missing",
                "bad_example": "Set seeds only when model training starts",
                "good_example": """# Set ALL random seeds in first config cell:
import random
import numpy as np
random.seed(42)
np.random.seed(42)""",
                "why_it_matters": "Early seed setting ensures all randomness is controlled from the start"
            }
        ]
    },
    2: {
        "name": "Write (Phase 2)",
        "description": "Fill sections with well-documented, organized code",
        "corrections": [
            {
                "issue": "Code without explanatory markdown",
                "severity": "MEDIUM",
                "problem": "Code cells lack markdown explaining what they do",
                "bad_example": """# Cell with 10 lines of code, no explanation
df = pd.merge(df1, df2, on='id')
df['col'] = df['col'].fillna(df['col'].mean())""",
                "good_example": """# Markdown cell:
## Merge and Imputation
# Combine datasets on ID and fill missing values with column mean

# Code cell:
df = pd.merge(df1, df2, on='id')
df['col'] = df['col'].fillna(df['col'].mean())""",
                "why_it_matters": "Markdown explanations help readers understand intent, not just code"
            },
            {
                "issue": "Repeated code patterns (3+)",
                "severity": "MEDIUM",
                "problem": "Same logic copied instead of factored into functions",
                "bad_example": "Same preprocessing repeated for each feature column",
                "good_example": """def preprocess_column(col):
    # Remove outliers, scale, encode
    return processed_col

# Apply to all columns
for col in columns:
    df[col] = preprocess_column(df[col])""",
                "why_it_matters": "Functions reduce duplication and make code easier to maintain"
            },
            {
                "issue": "Variables passed implicitly (global state)",
                "severity": "MEDIUM",
                "problem": "Code relies on values set in earlier cells without being passed",
                "bad_example": """# Cell 3: X_train = ...
# Cell 10: model.fit(X_train)  # No argument, relies on Cell 3""",
                "good_example": """# Pass explicitly between cells
def train_model(X_train, y_train):
    model.fit(X_train, y_train)
    return model""",
                "why_it_matters": "Explicit variable passing makes dependencies clear and cells reusable"
            }
        ]
    },
    3: {
        "name": "Validate (Phase 3)",
        "description": "Test work after each section, verify reproducibility",
        "corrections": [
            {
                "issue": "No idempotency checks",
                "severity": "HIGH",
                "problem": "Cells not tested for idempotency (run twice = same result)",
                "bad_example": "Append to file without checking if it exists first",
                "good_example": """# Check if file exists and is up-to-date
if not file_path.exists() or file_is_outdated():
    process_and_save()
else:
    load_existing()""",
                "why_it_matters": "Idempotent cells can be run multiple times safely"
            },
            {
                "issue": "Kernel not restarted between sections",
                "severity": "MEDIUM",
                "problem": "Section passes in editor but fails with fresh kernel",
                "bad_example": "Never test with clean kernel start",
                "good_example": """# After each major section:
# 1. Restart kernel
# 2. Run all cells from top
# 3. Verify outputs match expectations""",
                "why_it_matters": "Fresh kernel test catches hidden dependencies and confirms true reproducibility"
            },
            {
                "issue": "Artifacts not verified before next section",
                "severity": "MEDIUM",
                "problem": "Saved files not checked for correctness",
                "bad_example": "Save model and continue without verifying file exists",
                "good_example": """model_path = 'models/model.pkl'
joblib.dump(model, model_path)
assert Path(model_path).exists(), f'Model not saved: {model_path}'
print(f'✓ Model saved to {model_path}')""",
                "why_it_matters": "Artifact verification catches save failures immediately"
            }
        ]
    }
}

def get_audit_pass_corrections(pass_num):
    """Get correction suggestions for a specific audit pass."""
    return AUDIT_CORRECTIONS.get(pass_num, {})

def get_construction_phase_corrections(phase_num):
    """Get correction suggestions for a specific construction phase."""
    return CONSTRUCTION_CORRECTIONS.get(phase_num, {})

def get_all_audit_passes():
    """Get info about all audit passes."""
    return {k: {"name": v["name"], "description": v["description"]} 
            for k, v in AUDIT_CORRECTIONS.items()}

def get_all_construction_phases():
    """Get info about all construction phases."""
    return {k: {"name": v["name"], "description": v["description"]} 
            for k, v in CONSTRUCTION_CORRECTIONS.items()}
