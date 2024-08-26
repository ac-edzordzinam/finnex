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

# Function to calculate max loan amount
def calculate_max_loan_amount(customer_data_filtered):
    # Determine the maximum allowable loan amount (20 times the highest cash inflow)
    max_loan_amount = customer_data_filtered['TotalCashInflow'].max() * 20
    return max_loan_amount



# Function to check loan eligibility
def check_eligibility(customer_id):
    customer_data_filtered = customer_data[customer_data['CustomerID'] == customer_id]

    if customer_data_filtered.empty:
        return False, "Customer not found."

    # Checking consistency over 12 months for each feature
    credit_consistency = customer_data_filtered['TotalCallCreditPurchase'].rolling(window=12).min().iloc[-1] > 0
    data_consistency = customer_data_filtered['TotalDataPurchase'].rolling(window=12).min().iloc[-1] > 0
    inflow_consistency = customer_data_filtered['TotalCashInflow'].rolling(window=12).min().iloc[-1] > 0

  # Check if the customer is consistent in at least one of the three features
    if credit_consistency or data_consistency or inflow_consistency:
        max_loan_amount = calculate_max_loan_amount(customer_data_filtered)
        return True, f"Customer is eligible for a loan. The maximum allowable loan amount is {max_loan_amount:.2f} Ghana Cedis."
    else:
        return False, "Customer is not eligible for a loan based on consistency criteria."


# Function to calculate the repayment plan
def calculate_repayment_plan(customer_id, loan_amount):
    eligible, message = check_eligibility(customer_id)
    
    if not eligible:
        return None, message
    
    customer_data_filtered = customer_data[customer_data['CustomerID'] == customer_id]

    if customer_data_filtered.empty:
        return None, "Customer not found."

    # Get the maximum allowable loan amount using the external function
    max_loan_amount = calculate_max_loan_amount(customer_data_filtered)
    
    if loan_amount > max_loan_amount:
        return None, f"Requested loan amount exceeds the limit. The maximum allowable loan amount is {max_loan_amount:.2f} Ghana Cedis."

    # Start calculating the repayment plan
    repayment_plan = []
    remaining_loan = loan_amount
    cumulative_repayment = 0
    total_repayment_duration = 0 

    # List to store amounts for each month
    monthly_repayments = []

    # Use this to calculate the monthly repayment based on average inflow
    average_inflow = customer_data_filtered['TotalCashInflow'].mean()

    month_index = 0

    while remaining_loan > 0:
        # Wrap the month_index around if it exceeds the DataFrame length
        current_month_index = month_index % len(customer_data_filtered)
        
        # Get the current month's inflow
        current_inflow = customer_data_filtered.iloc[current_month_index]['TotalCashInflow']

        # If the total loan is less than or equal to the current inflow, pay off the loan in full
        if remaining_loan <= current_inflow:
            repayment = remaining_loan
        else:
            # Adjust repayment based on monthly inflow
            monthly_repayment = average_inflow * 0.1
            
            if current_inflow < 0.9 * average_inflow:
                repayment = monthly_repayment * 0.5
            elif current_inflow > 1.1 * average_inflow:
                repayment = monthly_repayment * 1.5
            else:
                repayment = monthly_repayment

        # Adjust the repayment in the last month if the remaining balance is less than the calculated monthly repayment
        if remaining_loan < repayment:
            repayment = remaining_loan
            remaining_loan = 0  # The loan is fully paid off
        else:
            remaining_loan -= repayment

        #cumulative_repayment += repayment
        total_repayment_duration += 1  # Increment the repayment duration

        # Store the repayment amount for this month
        monthly_repayments.append(repayment)

        repayment_plan.append({
            'Month': month_index + 1,
            'FlexibleRepayment': repayment,
           # 'CumulativeRepayment': cumulative_repayment,
            'RemainingLoan': max(0, remaining_loan)  # Ensure we don't show negative balance
        })

        month_index += 1
    #print(total_repayment_duration)
    # After the loop, calculate the simple interest (SI)
    
    R = 20  # 20% annual interest rate
    T = total_repayment_duration / 12  # Time in years
    P = loan_amount
    SI = (P * R * T) / 100  # Simple Interest
    MI =SI / total_repayment_duration
    #print(SI)

     # Reassign remaining_loan to include the simple interest
    remaining_loan = loan_amount + SI

    # Now, add the interest and update the cumulative repayment
    cumulative_repayment = 0
    for i in range(len(repayment_plan)):
        repayment_plan[i]['FlexibleRepayment'] += MI
        cumulative_repayment += repayment_plan[i]['FlexibleRepayment']
        repayment_plan[i]['CumulativeRepayment'] = cumulative_repayment
        repayment_plan[i]['RemainingLoan'] = remaining_loan - cumulative_repayment  # Update remaining loan with interest considered

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

     # Get the maximum allowable loan amount using the external function
    max_loan_amount = calculate_max_loan_amount(customer_data_filtered)
    
    if loan_amount > max_loan_amount:
        return None, f"Requested loan amount exceeds the limit. The maximum allowable loan amount is {max_loan_amount:.2f} Ghana Cedis."



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
                                    Provide a detailed analysis of the loan risk for the customer, including the debt-to-income ratio without showing the formula just the result, any financial stability concerns, and an overall risk assessment (e.g., Low Risk, Medium Risk, High Risk).""",
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
st.title("FinNex: AI-powered Financial Model  ")


# Placeholder for initial text or information
placeholder = st.empty()
#st.write("something")
placeholder.markdown(
    """
    ### Welcome to the Financial Nexus

This application is designed to assist in calculating flexible loan repayment plans, determining loan eligibility, and assessing loan risk based on detailed customer data.

### Overview:
- **Dataset**: The system contains data for 200 customers.
- **Eligibility Criteria**: A customer is eligible for a loan if they demonstrate consistency in at least one of the following areas for 12 months: Maximum amount eligible is calculated as 
20 times their highest income for longer term loans. 
  - **Credit Purchases**
  - **Data Purchases**
  - **Mobile Money (MoMo) Cash Inflow**
- **Flexible Repayment Plan**: The repayment plan is dynamically structured based on the customer's MoMo cash inflow, ensuring affordability during both high and low-income months.
- **Risk Assessment**: Loan risk is calculated by analyzing the customer's expenditure patterns and MoMo cash inflow, helping to gauge the potential risk associated with granting the loan.

### How to Use:
- Use the sidebar to input the customer's ID and the desired loan amount.
- Select an operation to either check loan eligibility, calculate a flexible repayment plan, or assess loan risk.

This tool offers a comprehensive and tailored approach to loan management, ensuring both customer satisfaction and financial security.
    """
)


st.sidebar.header("Input Parameters")
customer_id = st.sidebar.number_input("Customer ID", min_value=1, step=1)
loan_amount = st.sidebar.number_input("Loan Amount", min_value=1, step=1)

# Button to check eligibility
if st.sidebar.button("Check Loan Eligibility"):
    with st.spinner("Checking eligibility..."):
        eligible, message = check_eligibility(customer_id)
        placeholder.empty()  # Clear the placeholder content
        st.subheader("Eligibility Check")
        st.write(message)


# Button to assess loan risk
if st.sidebar.button("Assess Loan Risk"):
    with st.spinner("Assessing loan risk..."):
        placeholder.empty()  # Clear the placeholder content
        loan_risk = assess_loan_risk(customer_id, loan_amount)
        st.subheader("Loan Risk Assessment")
        st.write(loan_risk)
        

# Button to calculate repayment plan

if st.sidebar.button("Calculate Repayment Plan"):
    with st.spinner("Calculating..."):
        repayment_plan, error = calculate_repayment_plan(customer_id, loan_amount)
        
        placeholder.empty()  # Clear the placeholder content    

        if error:
            st.error(error)
        else:
            st.subheader("Repayment Plan")
            st.write(repayment_plan)


            
            prompt = (
                f"Customer ID: {customer_id}\n"
                f"Loan Amount: {loan_amount}\n\n"
                f"Repayment Plan:\n{repayment_plan.to_string(index=False)}\n\n"
                
                "Provide a summary of the repayment plan considering the flexible repayment amounts."
            )
            
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": """You are a knowledgeable agent specializing in the finance and loans domain in Ghana all currency is in Ghana cedis,do not show any formulas just results
                          who checks loan eligibility and structures flexible individual repayment plans and Total Loan Repayment (including the interest) based on total credit purchase, total data purchase, 
                          total cash in flow and occupation taking into consideration low and high months and structuring repayment plans  around those features.
                            State what would be payed fixed monthly through regular payments for different time periods and state the time periods for Total Loan Repayment (including the interest) if flexibilility is not accounted for.""",
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

