import streamlit as st
import pandas as pd
import io
import pypdfium2 as pdfium
import auth_system as auth
from datetime import datetime

# Import existing logic
from parse_generic import convert_generic
from parse_custom import convert_custom

# --- Configuration ---
st.set_page_config(page_title="PDF Pro by Akash", layout="wide", page_icon="🏦")

# --- Custom CSS for UI Improvements ---
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        font-weight: bold;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #555;
        text-align: center;
        margin-bottom: 30px;
    }
    .card {
        background-color: #f9f9f9;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
    }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def get_pdf_preview(pdf_bytes, password=None, page_idx=0):
    try:
        pdf = pdfium.PdfDocument(pdf_bytes, password=password)
        page = pdf[page_idx]
        bitmap = page.render(scale=2) # Render at 2x scale for quality
        pil_image = bitmap.to_pil()
        return pil_image, len(pdf)
    except Exception as e:
        return None, 0

# --- Session State Management ---
if 'user' not in st.session_state:
    st.session_state.user = None

# --- Views ---

def login_page():
    st.markdown('<div class="main-header">PDF Pro Login</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            tab1, tab2 = st.tabs(["Login", "Register"])
            
            with tab1:
                username = st.text_input("Username", key="login_user")
                password = st.text_input("Password", type="password", key="login_pass")
                if st.button("Login", type="primary"):
                    success, user_data = auth.authenticate(username, password)
                    if success:
                        st.session_state.user = user_data
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password")
            
            with tab2:
                new_user = st.text_input("Choose Username", key="reg_user")
                new_pass = st.text_input("Choose Password", type="password", key="reg_pass")
                if st.button("Register"):
                    if new_user and new_pass:
                        success, msg = auth.register_user(new_user, new_pass)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                    else:
                        st.warning("Please fill all fields")
            st.markdown('</div>', unsafe_allow_html=True)

def admin_dashboard():
    st.markdown('<div class="main-header">Admin Dashboard</div>', unsafe_allow_html=True)
    st.sidebar.button("Logout", on_click=logout)
    
    st.info("Manage Users and Licenses")
    
    # User List
    users = auth.get_all_users()
    df_users = pd.DataFrame(users)
    
    # Display nicely
    if not df_users.empty:
        display_cols = ["username", "role", "plan", "plan_expiry_date", "pages_used_cycle"]
        st.dataframe(df_users[display_cols], use_container_width=True)
    
    st.markdown("---")
    st.subheader("Assign License / Plan")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        target_user = st.selectbox("Select User", [u['username'] for u in users if u['role'] != 'admin'])
    with c2:
        plan = st.selectbox("Select Plan", ["Silver", "Gold", "Platinum", "None"])
    with c3:
        st.write("") # Spacer
        st.write("")
        if st.button("Assign Plan"):
            success, msg = auth.assign_plan(target_user, plan)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

def user_dashboard():
    user = st.session_state.user
    username = st.session_state.username
    
    # Refresh user data to get latest stats
    user = auth.get_user_info(username)
    
    st.sidebar.title(f"Welcome, {username}")
    st.sidebar.markdown(f"**Plan:** {user.get('plan', 'None')}")
    
    # Plan Details
    plan = user.get('plan', 'None')
    if plan == "Silver":
        limit = 100
        used = user.get('pages_used_cycle', 0)
        st.sidebar.progress(min(used/limit, 1.0))
        st.sidebar.caption(f"Usage: {used} / {limit} pages")
    elif plan in ["Gold", "Platinum"]:
        st.sidebar.success("Unlimited Access 🚀")
    
    st.sidebar.markdown(f"**Valid Till:** {user.get('plan_expiry_date')}")
    st.sidebar.markdown("---")
    st.sidebar.button("Logout", on_click=logout)

    st.markdown('<div class="main-header">🏦 Bank Statement Converter</div>', unsafe_allow_html=True)

    # Check Quota before showing tool
    allowed, msg = auth.check_quota(username, 0)
    if not allowed:
        st.error(f"🚫 Access Denied: {msg}")
        return

    # --- Converter Tool ---
    uploaded_file = st.file_uploader("Upload PDF Statement", type=["pdf"])
    password = st.text_input("PDF Password (if any)", type="password")

    if uploaded_file:
        pdf_bytes = uploaded_file.getvalue()
        
        # Preview
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Preview")
            preview_img, total_pages = get_pdf_preview(pdf_bytes, password)
            if preview_img:
                st.image(preview_img, caption="Page 1 Preview", use_container_width=True)
                st.caption(f"Total Pages: {total_pages}")
            else:
                st.error("Could not read PDF. Check password.")
                st.stop()

        with col2:
            st.subheader("Conversion Settings")
            
            bank_mode = st.selectbox("Select Bank / Mode", ["Generic", "Custom"])
            
            areas = None
            headers = None
            skip_rows = 0
            use_grid = False
            use_ocr = False
            merge_multi = False
            
            if bank_mode == "Custom":
                st.info("Custom Mode allows you to specify settings manually.")
                selection_mode = st.radio("Area Selection", ["Full Page", "Manual Coordinates (Advanced)"])
                
                if selection_mode == "Manual Coordinates (Advanced)":
                    st.markdown("Enter coordinates (x0, y0, x1, y1)")
                    c1, c2, c3, c4 = st.columns(4)
                    x0 = c1.number_input("X0", value=0)
                    y0 = c2.number_input("Y0", value=0)
                    x1 = c3.number_input("X1", value=595)
                    y1 = c4.number_input("Y1", value=842)
                    areas = {'all': [(x0, y0, x1, y1)]}
                
                headers_str = st.text_input("Column Headers (comma separated)", placeholder="Date, Desc, Debit, Credit, Balance")
                if headers_str:
                    headers = [h.strip() for h in headers_str.split(",") if h.strip()]
                    
                use_grid = st.checkbox("Use Grid Lines")
                use_ocr = st.checkbox("Use OCR")
                merge_multi = st.checkbox("Merge Multi-line Rows")
                skip_rows = st.number_input("Skip Top N Rows", min_value=0, value=0)

            # Convert Button
            if st.button("Convert PDF", type="primary"):
                # Check Quota again with actual page count
                allowed, msg = auth.check_quota(username, total_pages)
                if not allowed:
                    st.error(msg)
                    st.stop()

                with st.spinner("Processing..."):
                    try:
                        pdf_file_obj = io.BytesIO(pdf_bytes)
                        df = None
                        
                        if bank_mode == "Generic":
                            df = convert_generic(pdf_file_obj, password=password, areas=areas, return_df=True)
                        else:
                            df = convert_custom(
                                pdf_file_obj, password=password, areas=areas, headers=headers,
                                use_grid_lines=use_grid, use_ocr=use_ocr, merge_multiline=merge_multi,
                                skip_rows=skip_rows, return_df=True
                            )
                        
                        if df is not None and not df.empty:
                            st.success("Conversion Successful!")
                            
                            # Update Usage
                            auth.update_usage(username, total_pages)
                            
                            st.dataframe(df.head())
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df.to_excel(writer, index=False)
                            output.seek(0)
                            
                            file_name = uploaded_file.name.replace(".pdf", ".xlsx")
                            st.download_button(
                                label="Download Excel File",
                                data=output,
                                file_name=file_name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("No data found in the PDF.")
                            
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

def logout():
    st.session_state.user = None
    st.session_state.username = None
    st.rerun()

# --- Main Routing ---
if st.session_state.user is None:
    login_page()
else:
    if st.session_state.user['role'] == 'admin':
        admin_dashboard()
    else:
        user_dashboard()