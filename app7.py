import streamlit as st
import requests
import pandas as pd
import re
import time

st.set_page_config(page_title="Vaccine Pipeline Platform", page_icon="💉", layout="wide")

# ----------------------------
# Helper Functions
# ----------------------------

@st.cache_data(ttl=3600)
def fetch_all_vaccine_trials(disease, max_pages=10):
    """Fetch ALL vaccine trials by disease condition using pagination"""
    url = "https://clinicaltrials.gov/api/v2/studies"
    all_results = []
    page_token = None
    page_count = 0
    
    try:
        while page_count < max_pages:
            params = {
                "query.cond": disease, 
                "query.intr": "Vaccine", 
                "pageSize": 100  # Max allowed per page
            }
            if page_token:
                params["pageToken"] = page_token
            
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            studies = data.get("studies", [])
            if not studies:
                break
            
            for s in studies:
                proto = s.get("protocolSection", {})
                ident = proto.get("identificationModule", {})
                design = proto.get("designModule", {})
                status = proto.get("statusModule", {})
                sponsor = proto.get("sponsorCollaboratorsModule", {})
                arms = proto.get("armsInterventionsModule", {})

                # Extract vaccine names from this trial
                vaccines = set()
                for item in arms.get("interventions", []):
                    name = item.get("name")
                    if name:
                        vaccines.add(name.strip())
                for arm in arms.get("armGroups", []):
                    for name in arm.get("interventionNames", []):
                        vaccines.add(name.strip())

                nct_id = ident.get("nctId")
                title = ident.get("briefTitle") or ident.get("officialTitle") or "No title"
                phase = design.get("phases") or ["Not reported"]
                overall_status = status.get("overallStatus") or "Unknown"
                sponsor_name = sponsor.get("leadSponsor", {}).get("name", "Unknown")

                all_results.append({
                    "NCT ID": nct_id,
                    "Title": title,
                    "Phase": ", ".join(phase),
                    "Status": overall_status,
                    "Sponsor": sponsor_name,
                    "Vaccines": ", ".join(sorted(vaccines)) if vaccines else "Not reported"
                })
            
            # Check for next page
            page_token = data.get("nextPageToken")
            page_count += 1
            
            if not page_token:
                break
            
            # Respect rate limit
            time.sleep(1.2)  # ~50 requests per minute
        
        return all_results
    except requests.RequestException as e:
        st.error(f"Error fetching data: {e}")
        return []


@st.cache_data(ttl=3600)
def fetch_trial_details_with_vaccines(nct_id):
    """Fetch detailed trial info including vaccine names"""
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        proto = data.get("protocolSection", {})
        design = proto.get("designModule", {})
        status = proto.get("statusModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {})
        arms = proto.get("armsInterventionsModule", {})
        conditions = proto.get("conditionsModule", {})
        results_section = data.get("resultsSection", {})

        # Extract vaccine names
        vaccines = set()
        for item in arms.get("interventions", []):
            name = item.get("name")
            if name:
                vaccines.add(name.strip())
        for arm in arms.get("armGroups", []):
            for name in arm.get("interventionNames", []):
                vaccines.add(name.strip())

        # Extract conditions/diseases
        disease_list = conditions.get("conditions", [])

        # Extract outcomes
        outcomes = []
        if results_section:
            outcome_module = results_section.get("outcomeMeasuresModule", {})
            for o in outcome_module.get("outcomeMeasures", []):
                outcomes.append({
                    "Title": o.get("title"),
                    "Description": o.get("description", "")
                })

        # Basic info
        ident = proto.get("identificationModule", {})
        title = ident.get("briefTitle") or ident.get("officialTitle") or "No title"
        phases = design.get("phases") or ["Not reported"]
        overall_status = status.get("overallStatus", "Unknown")
        sponsor_name = sponsor.get("leadSponsor", {}).get("name", "Unknown")

        return {
            "Title": title,
            "Phase": ", ".join(phases),
            "Status": overall_status,
            "Sponsor": sponsor_name,
            "Vaccines": sorted(vaccines) if vaccines else ["Not reported"],
            "Diseases": disease_list,
            "Outcomes": outcomes
        }
    except requests.RequestException:
        return None


def extract_diseases_from_vaccine_trial(nct_id):
    """Extract disease conditions from a specific trial"""
    details = fetch_trial_details_with_vaccines(nct_id)
    if details and details.get("Diseases"):
        return details["Diseases"]
    return []


# ----------------------------
# Main App UI
# ----------------------------

st.title("💉 Vaccine Pipeline Platform")
st.markdown("""
Explore **complete vaccine trial data** from [ClinicalTrials.gov](https://clinicaltrials.gov/).  
Search by **disease condition** or **vaccine product name** with full competitor analysis.
""")

# Tabs for different search modes
tab1, tab2 = st.tabs(["🔍 Search by Disease", "💊 Search by Vaccine Product"])

# ----------------------------
# TAB 1: Search by Disease
# ----------------------------
with tab1:
    st.subheader("Search Vaccine Trials by Disease")
    st.markdown("💡 Fetches **all available trials** for the disease (no pagination limits)")
    
    disease = st.text_input("Enter Disease Name", value="RSV", key="disease_input")

    if st.button("🔍 Fetch All Trials", key="fetch_disease"):
        with st.spinner("Fetching all vaccine trials (this may take a moment)..."):
            studies = fetch_all_vaccine_trials(disease, max_pages=10)
            if not studies:
                st.warning(f"No vaccine studies found for '{disease}'. Try another disease.")
                st.session_state["studies"] = []
            else:
                st.session_state["studies"] = studies
                st.success(f"✅ Found **{len(studies)}** trials for **{disease}**!")

    # Display and filter studies
    studies = st.session_state.get("studies", [])
    
    if studies:
        df = pd.DataFrame(studies)

        # Sidebar filters
        st.sidebar.header("🎛️ Filters")
        phase_options = sorted({p for ph in df["Phase"] for p in ph.split(", ")})
        status_options = sorted(df["Status"].dropna().unique())

        selected_phases = st.sidebar.multiselect("Phase", options=phase_options, default=phase_options, key="phase_filter_disease")
        selected_status = st.sidebar.multiselect("Status", options=status_options, default=status_options, key="status_filter_disease")

        # Apply filters
        df_filtered = df[df["Phase"].apply(lambda x: any(ph in x for ph in selected_phases))]
        df_filtered = df_filtered[df_filtered["Status"].isin(selected_status)]

        st.info(f"📊 Showing **{len(df_filtered)}** of {len(studies)} trials")
        st.dataframe(df_filtered, use_container_width=True, height=400)

        # Study details
        selected_id = st.selectbox(
            "🔬 View Detailed Info",
            options=["Select a study..."] + df_filtered["NCT ID"].tolist(),
            key="select_disease_detail"
        )

        if selected_id != "Select a study...":
            with st.spinner("Loading details..."):
                details = fetch_trial_details_with_vaccines(selected_id)
            
            if details:
                st.markdown("---")
                st.subheader(f"📋 Study Details: {selected_id}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Title:** {details['Title']}")
                    st.markdown(f"**Phase:** {details['Phase']}")
                with col2:
                    st.markdown(f"**Status:** {details['Status']}")
                    st.markdown(f"**Sponsor:** {details['Sponsor']}")
                
                st.markdown("**💉 Vaccine Products:**")
                for v in details["Vaccines"]:
                    st.markdown(f"- {v}")
                
                if details["Outcomes"]:
                    st.markdown("**📊 Primary Outcome Measures:**")
                    for o in details["Outcomes"]:
                        st.write(f"• {o['Title']}")
                        if o["Description"]:
                            st.caption(o["Description"])
                else:
                    st.info("No outcomes reported yet.")
    else:
        st.info("👆 Enter a disease name and click **Fetch All Trials** to begin.")


# ----------------------------
# TAB 2: Search by Vaccine Product with Competitor Analysis
# ----------------------------
with tab2:
    st.subheader("Search Trials by Vaccine Product")
    st.markdown("🎯 Find trials for your vaccine + **competitor vaccines targeting the same disease**")
    
    vaccine_name = st.text_input("Enter Vaccine Product Name", value="", key="vaccine_input")

    if st.button("💊 Search Vaccine & Competitors", key="fetch_vaccine"):
        if not vaccine_name.strip():
            st.warning("Please enter a vaccine name.")
        else:
            with st.spinner(f"Step 1/2: Finding trials for '{vaccine_name}'..."):
                # First, search for the specific vaccine
                search_url = "https://clinicaltrials.gov/api/v2/studies"
                params = {"query.term": vaccine_name, "pageSize": 100}
                
                try:
                    resp = requests.get(search_url, params=params, timeout=20)
                    resp.raise_for_status()
                    data = resp.json()
                    studies = data.get("studies", [])
                    
                    if not studies:
                        st.warning(f"No trials found for vaccine '{vaccine_name}'.")
                        st.session_state["vaccine_trials"] = []
                        st.session_state["competitor_trials"] = []
                    else:
                        # Extract diseases from the first matching trial
                        first_nct = studies[0].get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                        diseases = extract_diseases_from_vaccine_trial(first_nct) if first_nct else []
                        
                        st.session_state["target_vaccine"] = vaccine_name
                        st.session_state["target_diseases"] = diseases
                        
                        # Process vaccine trials
                        vaccine_results = []
                        for study in studies:
                            proto = study.get("protocolSection", {})
                            ident = proto.get("identificationModule", {})
                            design = proto.get("designModule", {})
                            status = proto.get("statusModule", {})
                            sponsor = proto.get("sponsorCollaboratorsModule", {})
                            arms = proto.get("armsInterventionsModule", {})
                            
                            vaccines = set()
                            for item in arms.get("interventions", []):
                                name = item.get("name")
                                if name:
                                    vaccines.add(name.strip())
                            
                            vaccine_list = [v.lower() for v in vaccines]
                            if vaccine_name.lower() in " ".join(vaccine_list):
                                vaccine_results.append({
                                    "NCT ID": ident.get("nctId"),
                                    "Title": ident.get("briefTitle") or ident.get("officialTitle") or "No title",
                                    "Phase": ", ".join(design.get("phases") or ["Not reported"]),
                                    "Status": status.get("overallStatus") or "Unknown",
                                    "Sponsor": sponsor.get("leadSponsor", {}).get("name", "Unknown"),
                                    "Vaccines": ", ".join(sorted(vaccines)) if vaccines else "Not reported"
                                })
                        
                        st.session_state["vaccine_trials"] = vaccine_results
                        
                        # Fetch competitor trials for same diseases
                        if diseases:
                            with st.spinner(f"Step 2/2: Finding competitor vaccines for {', '.join(diseases[:2])}..."):
                                competitor_trials = fetch_all_vaccine_trials(diseases[0], max_pages=5)
                                
                                # Filter out the target vaccine from competitors
                                competitor_trials = [
                                    trial for trial in competitor_trials 
                                    if vaccine_name.lower() not in trial["Vaccines"].lower()
                                ]
                                
                                st.session_state["competitor_trials"] = competitor_trials
                                st.success(f"✅ Found {len(vaccine_results)} trials for **{vaccine_name}** and {len(competitor_trials)} competitor trials!")
                        else:
                            st.session_state["competitor_trials"] = []
                            st.success(f"✅ Found {len(vaccine_results)} trials for **{vaccine_name}**")
                
                except requests.RequestException as e:
                    st.error(f"Search failed: {e}")
                    st.session_state["vaccine_trials"] = []
                    st.session_state["competitor_trials"] = []

    # Display vaccine trials
    vaccine_trials = st.session_state.get("vaccine_trials", [])
    competitor_trials = st.session_state.get("competitor_trials", [])
    target_vaccine = st.session_state.get("target_vaccine", "")
    target_diseases = st.session_state.get("target_diseases", [])
    
    if vaccine_trials:
        st.markdown("---")
        st.subheader(f"🎯 Your Vaccine: {target_vaccine}")
        if target_diseases:
            st.caption(f"Primary Disease(s): {', '.join(target_diseases)}")
        
        df_vaccine = pd.DataFrame(vaccine_trials)
        st.info(f"📊 Found **{len(df_vaccine)}** trials")
        st.dataframe(df_vaccine, use_container_width=True, height=300)

        # Study details for target vaccine
        selected_vaccine_id = st.selectbox(
            "🔬 View Detailed Info",
            options=["Select a study..."] + df_vaccine["NCT ID"].tolist(),
            key="select_vaccine_detail"
        )

        if selected_vaccine_id != "Select a study...":
            with st.spinner("Loading details..."):
                details_v = fetch_trial_details_with_vaccines(selected_vaccine_id)
            
            if details_v:
                st.markdown("---")
                st.subheader(f"📋 Study Details: {selected_vaccine_id}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Title:** {details_v['Title']}")
                    st.markdown(f"**Phase:** {details_v['Phase']}")
                with col2:
                    st.markdown(f"**Status:** {details_v['Status']}")
                    st.markdown(f"**Sponsor:** {details_v['Sponsor']}")
                
                st.markdown("**💉 Vaccine Products:**")
                for v in details_v["Vaccines"]:
                    st.markdown(f"- {v}")
                
                if details_v["Outcomes"]:
                    st.markdown("**📊 Primary Outcome Measures:**")
                    for o in details_v["Outcomes"]:
                        st.write(f"• {o['Title']}")
                        if o["Description"]:
                            st.caption(o["Description"])

    # Display competitor analysis
    if competitor_trials:
        st.markdown("---")
        st.subheader(f"🔄 Competitor Vaccines for {', '.join(target_diseases) if target_diseases else 'Same Disease'}")
        st.caption("All other vaccines targeting the same disease condition")
        
        df_competitor = pd.DataFrame(competitor_trials)
        
        # Competitor filters
        st.sidebar.header("🎛️ Competitor Filters")
        phase_options_c = sorted({p for ph in df_competitor["Phase"] for p in ph.split(", ")})
        status_options_c = sorted(df_competitor["Status"].dropna().unique())

        selected_phases_c = st.sidebar.multiselect("Phase", options=phase_options_c, default=phase_options_c, key="phase_filter_comp")
        selected_status_c = st.sidebar.multiselect("Status", options=status_options_c, default=status_options_c, key="status_filter_comp")

        # Apply filters
        df_competitor_filtered = df_competitor[df_competitor["Phase"].apply(lambda x: any(ph in x for ph in selected_phases_c))]
        df_competitor_filtered = df_competitor_filtered[df_competitor_filtered["Status"].isin(selected_status_c)]

        st.info(f"📊 Showing **{len(df_competitor_filtered)}** of {len(competitor_trials)} competitor trials")
        st.dataframe(df_competitor_filtered, use_container_width=True, height=400)

        # Competitor details
        selected_comp_id = st.selectbox(
            "🔬 View Competitor Trial Details",
            options=["Select a study..."] + df_competitor_filtered["NCT ID"].tolist(),
            key="select_comp_detail"
        )

        if selected_comp_id != "Select a study...":
            with st.spinner("Loading details..."):
                details_c = fetch_trial_details_with_vaccines(selected_comp_id)
            
            if details_c:
                st.markdown("---")
                st.subheader(f"📋 Competitor Study: {selected_comp_id}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Title:** {details_c['Title']}")
                    st.markdown(f"**Phase:** {details_c['Phase']}")
                with col2:
                    st.markdown(f"**Status:** {details_c['Status']}")
                    st.markdown(f"**Sponsor:** {details_c['Sponsor']}")
                
                st.markdown("**💉 Vaccine Products:**")
                for v in details_c["Vaccines"]:
                    st.markdown(f"- {v}")
                
                if details_c["Outcomes"]:
                    st.markdown("**📊 Primary Outcome Measures:**")
                    for o in details_c["Outcomes"]:
                        st.write(f"• {o['Title']}")
                        if o["Description"]:
                            st.caption(o["Description"])
    
    if not vaccine_trials and not competitor_trials:
        st.info("👆 Enter a vaccine product name and click **Search Vaccine & Competitors** to begin.")


# ----------------------------
# Footer
# ----------------------------
st.markdown("---")
st.caption("💡 **Vaccine Pipeline Platform** | Data from ClinicalTrials.gov | Developed by Aman & Smriti")