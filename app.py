# app.py
import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Vaccine Pipeline Platform", page_icon="💉", layout="wide")
st.title("💉 Vaccine Pipeline Platform Prototype")

st.markdown("""
Explore **live vaccine trial data** from [ClinicalTrials.gov](https://clinicaltrials.gov/).
Type any disease name and explore vaccine studies worldwide.
Use the sidebar to filter by **Phase** or **Status**.
""")

# ----------------------------
# Fetch list of studies
# ----------------------------
@st.cache_data(ttl=3600)
def fetch_vaccine_data(disease, limit=50):
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {"query.cond": disease, "query.intr": "Vaccine", "pageSize": limit}
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        studies = resp.json().get("studies", [])
        if not studies:
            return []  # no studies found
        results = []
        for s in studies:
            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            design = proto.get("designModule", {})
            status = proto.get("statusModule", {})
            sponsor = proto.get("sponsorCollaboratorsModule", {})

            nct_id = ident.get("nctId")
            title = ident.get("briefTitle") or ident.get("officialTitle") or "No title"
            phase = design.get("phases") or ["Not reported"]
            overall_status = status.get("overallStatus") or "Unknown"
            sponsor_name = sponsor.get("leadSponsor", {}).get("name", "Unknown")

            results.append({
                "NCT ID": nct_id,
                "Title": title,
                "Phase": ", ".join(phase),
                "Status": overall_status,
                "Sponsor": sponsor_name
            })
        return results
    except requests.RequestException as e:
        st.error(f"Error fetching data: {e}")
        return []

# ----------------------------
# Fetch detailed info for a study
# ----------------------------
@st.cache_data(ttl=3600)
def fetch_trial_details(nct_id):
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        proto = data.get("protocolSection", {})
        design = proto.get("designModule", {})
        status = proto.get("statusModule", {})
        results_section = data.get("resultsSection", {})

        # Phase
        phases = design.get("phases") or ["Not reported"]

        # Outcomes
        outcomes = []
        if results_section:
            outcome_module = results_section.get("outcomeMeasuresModule", {})
            for o in outcome_module.get("outcomeMeasures", []):
                outcomes.append({
                    "Title": o.get("title"),
                    "Description": o.get("description", "")
                })

        # Basic info
        title = proto.get("identificationModule", {}).get("briefTitle") or proto.get("identificationModule", {}).get("officialTitle") or "No title"
        sponsor = proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "Unknown")
        overall_status = status.get("overallStatus") or "Unknown"

        return {
            "Title": title,
            "Phase": ", ".join(phases),
            "Status": overall_status,
            "Sponsor": sponsor,
            "Outcomes": outcomes
        }
    except requests.RequestException:
        return None

# ----------------------------
# Sidebar controls
# ----------------------------
disease = st.text_input("Enter Disease Name", value="RSV")
limit = st.slider("Number of Studies to Fetch", 5, 50, 20)

if st.button("Fetch Data"):
    studies = fetch_vaccine_data(disease, limit)
    if not studies:
        st.warning(f"No vaccine studies found for '{disease}'. Please try another disease.")
        st.session_state["studies"] = []
    else:
        st.session_state["studies"] = studies

# Filter and display studies
studies = st.session_state.get("studies", [])

if studies:
    df = pd.DataFrame(studies)

    # Sidebar filters
    st.sidebar.header("Filters")
    phase_options = sorted({p for ph in df["Phase"] for p in ph.split(", ")})
    status_options = sorted(df["Status"].dropna().unique())

    selected_phases = st.sidebar.multiselect("Filter by Phase", options=phase_options, default=phase_options)
    selected_status = st.sidebar.multiselect("Filter by Status", options=status_options, default=status_options)

    # Apply filters
    df_filtered = df[df["Phase"].apply(lambda x: any(ph in x for ph in selected_phases))]
    df_filtered = df_filtered[df_filtered["Status"].isin(selected_status)]

    st.success(f"Showing {len(df_filtered)} studies after filtering!")
    st.dataframe(df_filtered, use_container_width=True)

    # Select study for detailed view
    selected_id = st.selectbox(
        "🔍 View Details for a Specific Study",
        options=["Select"] + df_filtered["NCT ID"].tolist()
    )

    if selected_id != "Select":
        details = fetch_trial_details(selected_id)
        if details:
            st.subheader(f"Study Details: {selected_id}")
            st.write(f"**Title:** {details['Title']}")
            st.write(f"**Phase:** {details['Phase']}")
            st.write(f"**Status:** {details['Status']}")
            st.write(f"**Sponsor:** {details['Sponsor']}")
            if details["Outcomes"]:
                st.markdown("**Primary Outcome Measures:**")
                for o in details["Outcomes"]:
                    st.write(f"- {o['Title']}")
                    if o["Description"]:
                        st.caption(o["Description"])
            else:
                st.info("No outcomes reported yet for this study.")
else:
    st.info("No studies fetched yet. Enter a disease and click 'Fetch Data'.")

st.markdown("---")
st.caption("Developed as part of the Vaccine Pipeline MVP by Aman and Smriti.")
