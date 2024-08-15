import streamlit as st
import pandas as pd
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
# Load the customer data
@st.cache_data
def load_data():
    return pd.read_excel('./final_combined_customer_data.xlsx')

customer_data = load_data()

api_key = os.environ.get("OPENAI_API_KEY") or st.secrets["OPENAI_API_KEY"] 
client = OpenAI(api_key=api_key,)


# Function to check loan eligibility
def check_eligibility(customer_id):
    customer_data_filtered = customer_data[customer_data['CustomerID'] == customer_id]

    if customer_data_filtered.empty:
        return False, "Customer not found."

    # Checking consistency over 12 months for each feature
    credit_consistency = customer_data_filtered['TotalCallCreditPurchase'].rolling(window=11).min().iloc[-1] > 0
    data_consistency = customer_data_filtered['TotalDataPurchase'].rolling(window=11).min().iloc[-1] > 0
    inflow_consistency = customer_data_filtered['TotalCashInflow'].rolling(window=11).min().iloc[-1] > 0

    if credit_consistency or data_consistency or inflow_consistency:
        return True, "Customer is eligible for a loan."
    else:
        return False, "Customer is not eligible for a loan."



# Function to calculate the repayment plan
def calculate_repayment_plan(customer_id, loan_amount):
    eligible, message = check_eligibility(customer_id)
    
    if not eligible:
        return None, message


    
    customer_data_filtered = customer_data[customer_data['CustomerID'] == customer_id]

    if customer_data_filtered.empty:
        return None, "Customer not found."

    # Add 20% interest to the loan amount
    total_loan = loan_amount * 1.2

    # Start calculating the repayment plan
    repayment_plan = []
    remaining_loan = total_loan

    # Determine the average inflow to calculate the monthly repayment
    average_inflow = customer_data_filtered['TotalCashInflow'].mean()
    monthly_repayment = average_inflow * 0.1

    month_index = 0

    while remaining_loan > 0:
        if month_index >= len(customer_data_filtered):
            current_inflow = average_inflow  # Use average if we exceed data length
        else:
            current_inflow = customer_data_filtered.iloc[month_index]['TotalCashInflow']

        # Adjust repayment based on monthly inflow
        if current_inflow < 0.9 * average_inflow:
            repayment = monthly_repayment * 0.5
        elif current_inflow > 1.1 * average_inflow:
            repayment = monthly_repayment * 1.5
        else:
            repayment = monthly_repayment

        remaining_loan -= repayment
        repayment_plan.append({
            'Month': month_index + 1,
            'FlexibleRepayment': repayment,
            'CumulativeRepayment': total_loan - remaining_loan,
            'RemainingLoan': max(0, remaining_loan)  # Ensure we don't show negative balance
        })

        month_index += 1

    repayment_df = pd.DataFrame(repayment_plan)

    return repayment_df, None

# Function to assess loan risk
def assess_loan_risk(customer_id, loan_amount):
    eligible, message = check_eligibility(customer_id)
    
    if not eligible:
        return None, message
    
    
    customer_data_filtered = customer_data[customer_data['CustomerID'] == customer_id]

    if customer_data_filtered.empty:
        return "Customer not found."

    

    customer_summary = customer_data_filtered.describe().to_string()

    prompt = (
        f"Customer ID: {customer_id}\n"
        f"Loan Amount: {loan_amount}\n"
        f"Customer Data Summary:\n{customer_summary}\n\n"
        "Based on this data, assess the loan risk and provide a brief explanation."
    )

    chat_completion = client.chat.completions.create(
        messages=[
                    {
                        "role": "system",
                        "content": """You are a knowledgeable agent specializing in the finance and loans domain in Ghana all currency is in Ghana cedis, Consider factors such as average cash inflow, spending patterns, and the overall financial stability of the customer.
                                    Provide a detailed analysis of the loan risk for Customer 167, including the debt-to-income ratio, any financial stability concerns, and an overall risk assessment (e.g., Low Risk, Medium Risk, High Risk).""",
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                model="gpt-4o",
            )

    loan_risk_assessment = chat_completion.choices[0].message.content
    
    return loan_risk_assessment

# Streamlit interface
st.title("Flexible Loan Repayment Plan Calculator")

st.sidebar.header("Input Parameters")
customer_id = st.sidebar.number_input("Customer ID", min_value=1, step=1)
loan_amount = st.sidebar.number_input("Loan Amount", min_value=1, step=1)

# Button to check eligibility
if st.sidebar.button("Check Loan Eligibility"):
    with st.spinner("Checking eligibility..."):
        eligible, message = check_eligibility(customer_id)
        st.subheader("Eligibility Check")
        st.write(message)

# Button to calculate repayment plan
if st.sidebar.button("Calculate Repayment Plan"):
    with st.spinner("Calculating..."):
        repayment_plan, error = calculate_repayment_plan(customer_id, loan_amount)
        
        if error:
            st.error(error)
        else:
            st.subheader("Repayment Plan")
            st.write(repayment_plan)


            
            prompt = f"Customer ID: {customer_id}\nLoan Amount: {loan_amount}\n\nRepayment Plan:\n{repayment_plan.to_string(index=False)}\n\nProvide a summary of the repayment plan considering the flexible repayment amounts."

            
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": """You are a knowledgeable agent specializing in the finance and loans domain in Ghana all currency is in Ghana cedis, who checks loan eligibility and structures flexible individual repayment plans based on total credit purchase, total data purchase, total cash in flow and occupation 
                                taking into consideration low and high months and structuring repayment plans around those features, use the customers overall consistency to verify eligibility customer should be consistent for 12 months on at least one of the three features total credit purchase, total data purchase, total cash in flow""",
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                model="gpt-4o",
            )
            
            summary = chat_completion.choices[0].message.content
            st.subheader("Summary")
            st.write(summary)

# Button to assess loan risk
if st.sidebar.button("Assess Loan Risk"):
    with st.spinner("Assessing loan risk..."):
        loan_risk = assess_loan_risk(customer_id, loan_amount)
        st.subheader("Loan Risk Assessment")
        st.write(loan_risk)