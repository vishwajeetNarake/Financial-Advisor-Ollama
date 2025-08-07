import requests

def format_prompt(user_data):
    # You can customize this more depending on the fields you need
    return f"""
    Provide financial advice for a person with the following details:
    - Name: {user_data.get('name')}
    - Age: {user_data.get('age')}
    - Occupation: {user_data.get('occupation')}
    - Annual Income: {user_data.get('annualIncome')}
    - Loan Amount: {user_data.get('loanAmount')}
    - Loan Purpose: {user_data.get('loanPurpose')}
    - Credit Score: {user_data.get('creditScore')}
    - Existing Debt: {user_data.get('existingDebt')}
    - Monthly Expenses: {user_data.get('monthlyExpenses')}
    - Savings: {user_data.get('savings')}
    - Loan Type: {user_data.get('loanType')}
    - Repayment Structure: {user_data.get('repaymentStructure')}
    - Risk Tolerance: {user_data.get('riskTolerance')}
    """

import requests

def query_ollama(prompt):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "ALIENTELLIGENCE/financialadvisor",
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("response", "⚠️ Error: No response key in Ollama output.")
    except Exception as e:
        return f"⚠️ Error calling Ollama: {e}"

