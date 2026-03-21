import pandas as pd
import os

def analyze_csv(file_path):
    print(f"\n📂 FILE: {file_path}")
    
    df = pd.read_csv(file_path)
    
    print("Shape:", df.shape)
    print("\nColumns:", df.columns.tolist())
    
    print("\nSample Rows:")
    print(df.head(3))
    
    print("\nNull Values:")
    print(df.isnull().sum())
    
    print("\nUnique Values Per Column:")
    for col in df.columns:
        print(f"{col}: {df[col].nunique()} unique values")

    print("\n" + "="*60)


def main():
    base_path = "data/raw/medical"

    files = [
        "Symptom2Disease.csv",
        "Disease_symptom_and_patient_profile_dataset.csv",
        "Disease precaution.csv",
        "sample_hybrid_triage_dataset.csv"
    ]

    for file in files:
        path = os.path.join(base_path, file)
        if os.path.exists(path):
            analyze_csv(path)
        else:
            print(f"❌ Missing: {file}")

if __name__ == "__main__":
    main()