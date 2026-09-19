import streamlit as st


st.set_page_config(
    page_title="Nash Shipping Document Verifier",
    page_icon="📄",
    layout="wide",
)

st.title("Shipping Document Verification")
st.caption("Team Nash")

st.write(
    "Select an email to review its classification and compare the Shipping "
    "Instruction with the draft Bill of Lading."
)

email_id = st.selectbox(
    "Select an email",
    ["email_001", "email_002", "email_004"],
)

if st.button("Run verification", type="primary"):
    st.info(f"The verification workflow for {email_id} will be connected next.")
