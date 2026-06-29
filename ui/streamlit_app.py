from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.report_service import ReportService


def main() -> None:
    st.set_page_config(page_title="Generic Report Tool", layout="wide")
    st.title("Generic Report Tool")

    service = ReportService(
        config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR", str(ROOT / "config")),
        data_dir=os.environ.get("GENERIC_REPORT_DATA_DIR", str(ROOT / "data")),
        public_base_url=os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL", "http://localhost:8810"),
    )

    brands = service.loader.list_brands()
    brand_ids = [item["brand_id"] for item in brands] or ["default"]
    brand_id = st.selectbox("Brand", brand_ids)
    candidate_name = st.text_input("Candidate Name")
    position_title = st.text_input("Position Title")
    current_company = st.text_input("Current Company")
    current_title = st.text_input("Current Title")
    job_description = st.text_area("Job Description", height=120)
    resume_text = st.text_area("Resume Text", height=220)

    if st.button("Create Draft", type="primary"):
        draft = service.create_draft({
            "brand_id": brand_id,
            "candidate_name": candidate_name,
            "position_title": position_title,
            "current_company": current_company,
            "current_title": current_title,
            "job_description": job_description,
            "resume_text": resume_text,
        })
        st.session_state["report_id"] = draft["report_id"]
        st.json(draft)

    report_id = st.session_state.get("report_id")
    if report_id:
        st.divider()
        st.subheader("Draft Actions")
        if st.button("Generate Comments"):
            st.json(service.generate_comments(report_id))
        if st.button("Render DOCX"):
            rendered = service.render_report(report_id)
            st.json(rendered)
            path = service.output_path(rendered["filename"])
            st.download_button("Download DOCX", path.read_bytes(), file_name=rendered["filename"])


if __name__ == "__main__":
    main()
