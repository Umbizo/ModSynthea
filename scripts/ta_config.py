TA_CONFIG = {
    # ---------------------------------------------------------------- Cardiology
    "HTN": {
        "name": "Hypertension",
        "board_area": "Cardiology",
        "board_exists": True,
        "board_patients": 171205,
        "sheet": "ai_hypertension",
        "dx_categories": ["INDICATION"],
        "module_stems": ["hypertension"],
        # Antihypertensives are oral and dispensed -> Part D NDC, not Part B HCPCS.
        "partb_expected": False,
    },
    "AFIB": {
        "name": "Atrial Fibrillation",
        "board_area": "Cardiology",
        "board_exists": True,
        "board_patients": 26704,
        "sheet": "afib",
        "dx_categories": ["ATRIAL FIBRILLATION (AFIB)"],
        "module_stems": ["atrial_fibrillation"],
        # Rate/rhythm control and the DOACs are oral -> Part D.
        "partb_expected": False,
    },
    "HF": {
        "name": "Heart Failure",
        "board_area": "Cardiology",
        "board_exists": True,
        "board_patients": None,  # board leaves this blank
        "sheet": "heart_failure",
        "dx_categories": ["HF"],
        "module_stems": ["heart_failure", "congestive_heart_failure"],
        # 623 NDC vs 4 HCPCS in the sheet: this is a Part D therapeutic area.
        "partb_expected": False,
    },
    "CAD": {
        "name": "Coronary Artery Disease",
        "board_area": "Cardiology",
        "board_exists": True,
        "board_patients": 3626,
        "sheet": "ai_coronary_artery_disease",
        "dx_categories": ["INDICATION", "ACUTE MI", "ACUTE ISCHEMIA"],
        "module_stems": ["coronary_artery_disease", "coronary_heart_disease"],
        # Sheet carries CPT procedures and no HCPCS drugs.
        "partb_expected": False,
    },
    # ---------------------------------------------------------------- Oncology
    "OVARIAN": {
        "name": "Ovarian Cancer",
        "board_area": "Oncology",
        "board_exists": False,
        "board_patients": 0,
        "sheet": "ovarian_cancer",
        "dx_categories": ["INDICATION"],
        "module_stems": ["ovarian_cancer"],
        "partb_expected": True,
    },
    "PROSTATE": {
        "name": "Prostate Cancer",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 1244,
        "sheet": "prostate_cancer",
        # INDICATION also carries D075, D400, R9721 (raised PSA) and the Z19 hormone
        # sensitivity codes. Kept as authored -- section 2.2 breaks the cohort down by
        # code, so a cohort resting on raised-PSA codes is visible rather than hidden.
        "dx_categories": ["INDICATION"],
        "module_stems": ["prostate_cancer"],
        "partb_expected": True,
    },
    "BLADDER": {
        "name": "Bladder Cancer",
        "board_area": "Oncology",
        "board_exists": False,
        "board_patients": 1483,
        "sheet": "bladder_cancer",
        # INDICATION spans C65-C68 by design: the whole urothelial tract, not just C67.
        "dx_categories": ["INDICATION"],
        "module_stems": ["bladder_cancer"],
        "partb_expected": True,
    },
    "ENDOMETRIAL": {
        "name": "Endometrial Cancer",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 12778,
        "sheet": "endometrial_cancer",
        "dx_categories": ["INDICATION"],
        "module_stems": ["endometrial_cancer", "uterine_cancer"],
        "partb_expected": True,
    },
    "NSCLC": {
        "name": "Non Small Cell Lung Cancer",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 10599,
        "sheet": "nsclc",
        "dx_categories": ["INDICATION"],
        "module_stems": ["non_small_cell_lung_cancer", "nsclc"],
        "partb_expected": True,
    },
    "SCLC": {
        "name": "Small Cell Lung Cancer",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 24018,
        "sheet": "lung_cancer",
        # ICD-10 does not encode histology. C34.9x is the closest available proxy and
        # is what the previous revision of this notebook used; kept for continuity.
        "dx_categories": ["INDICATION"],
        "dx_restrict": ["C3490", "C3491", "C3492"],
        "module_stems": ["small_cell_lung_cancer", "sclc"],
        "partb_expected": True,
    },
    "LUNG": {
        "name": "Lung Cancer (all histologies)",
        "board_area": "Oncology (supplementary)",
        "board_exists": None,
        "board_patients": None,
        "sheet": "lung_cancer",
        "dx_categories": ["INDICATION"],
        "module_stems": ["lung_cancer"],
        "partb_expected": True,
    },
    "CRC": {
        "name": "Colorectal Cancer",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 64330,
        "sheet": "colorectal_cancer",
        "dx_categories": ["INDICATION"],
        "module_stems": ["colorectal_cancer"],
        "partb_expected": True,
    },
    "COLON": {
        "name": "Colon Cancer (sub-split of CRC)",
        "board_area": "Oncology (supplementary)",
        "board_exists": None,
        "board_patients": None,
        "sheet": "colorectal_cancer",
        "dx_categories": ["INDICATION"],
        "dx_restrict": ["C18"],
        "module_stems": ["colorectal_cancer"],
        "partb_expected": True,
    },
    "RECTAL": {
        "name": "Rectal Cancer (sub-split of CRC)",
        "board_area": "Oncology (supplementary)",
        "board_exists": None,
        "board_patients": None,
        "sheet": "colorectal_cancer",
        "dx_categories": ["INDICATION"],
        "dx_restrict": ["C19", "C20"],
        "module_stems": ["colorectal_cancer"],
        "partb_expected": True,
    },
    "PANC": {
        "name": "Pancreatic Cancer",
        "board_area": "Oncology",
        "board_exists": False,
        "board_patients": 2,
        "sheet": "ai_pancreatic_cancer",
        "dx_categories": ["INDICATION"],
        "module_stems": ["pancreatic_cancer"],
        "partb_expected": True,
    },
    "AML": {
        "name": "Acute Myeloid Leukaemia",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 415,
        "sheet": "aml",
        "dx_categories": ["AML DIAGNOSIS", "AML_INDICATION"],
        "module_stems": ["acute_myeloid_leukemia", "aml"],
        "partb_expected": True,
    },
    "PV": {
        "name": "Polycythemia Vera",
        "board_area": "Oncology",
        "board_exists": True,
        "board_patients": 4889,
        "sheet": "polycythemia_vera",
        "dx_categories": ["PV_INDICATION"],
        "module_stems": ["polycythemia_vera"],
        # Hydroxyurea and ruxolitinib are oral; 209 NDC vs 6 HCPCS in the sheet.
        "partb_expected": False,
    },
    # ---------------------------------------------------------------- Haematology
    "MM": {
        "name": "Multiple Myeloma",
        "board_area": "Hematology",
        "board_exists": True,
        "board_patients": 18643,
        "sheet": "multiple_myeloma",
        "dx_categories": ["INDICATION", "MM_PRECURSOR"],
        "module_stems": ["multiple_myeloma"],
        "partb_expected": True,
    },
    "DLBCL": {
        "name": "Diffuse Large B-Cell Lymphoma",
        "board_area": "Hematology",
        "board_exists": True,
        "board_patients": 387,
        "sheet": "dlbcl",
        "dx_categories": ["DLBCL_INDICATION", "INDICATION"],
        "module_stems": ["dlbcl", "diffuse_large_b_cell_lymphoma"],
        "partb_expected": True,
    },
    "MCL": {
        "name": "Mantle Cell Lymphoma",
        "board_area": "Hematology",
        "board_exists": True,
        "board_patients": 164,
        "sheet": "mantle_cell_lymphoma",
        "dx_categories": ["MCL_INDICATION"],
        "module_stems": ["mantle_cell_lymphoma"],
        "partb_expected": True,
    },
    "ALL": {
        "name": "Acute Lymphoblastic Leukaemia",
        "board_area": "Hematology",
        "board_exists": True,
        "board_patients": 1987,
        "sheet": "ai_acute_lymphoblastic_leukemia",
        "dx_categories": ["INDICATION"],
        "module_stems": ["acute_lymphoblastic_leukemia"],
        "partb_expected": True,
    },
    "FL": {
        "name": "Follicular Lymphoma",
        "board_area": "Hematology (supplementary)",
        "board_exists": None,
        "board_patients": None,
        "sheet": "follicular_lymphoma",
        "dx_categories": ["FL_INDICATION"],
        "module_stems": ["follicular_lymphoma"],
        "partb_expected": True,
    },
    # ---------------------------------------------------------------- Ophthalmology
    "DME": {
        "name": "Diabetic Macular Edema",
        "board_area": "Ophthalmology",
        "board_exists": None,  # board leaves this blank
        "board_patients": 407,
        "sheet": "retinal_disease",
        "dx_categories": ["DME"],
        "module_stems": ["diabetic_macular_edema", "macular_edema"],
        "partb_expected": True,
    },
    "WAMD": {
        "name": "Wet Age-Related Macular Degeneration",
        "board_area": "Ophthalmology",
        "board_exists": True,
        "board_patients": 3627,
        "sheet": "retinal_disease",
        "dx_categories": ["WAMD"],
        "module_stems": ["wet_macular_degeneration", "macular_degeneration", "wamd"],
        "partb_expected": True,
    },
    "DR": {
        "name": "Diabetic Retinopathy",
        "board_area": "Ophthalmology",
        "board_exists": True,
        "board_patients": 3598,
        "sheet": "retinal_disease",
        # Superset of DME by construction: the DR codes include the E**.31x parents.
        "dx_categories": ["DIABETIC RETINOPATHY"],
        "module_stems": ["diabetic_retinopathy"],
        "partb_expected": True,
    },
    # ---------------------------------------------------------------- Nephrology
    "AKI": {
        "name": "Acute Kidney Injury",
        "board_area": "Nephrology",
        "board_exists": True,
        "board_patients": 2768,
        "sheet": "ai_acute_kidney_injury",
        "dx_categories": ["INDICATION"],
        "module_stems": ["acute_kidney_injury"],
        "partb_expected": False,
    },
    "PKD": {
        "name": "Polycystic Kidney Disease",
        "board_area": "Nephrology",
        "board_exists": True,
        "board_patients": 126,
        "sheet": "ai_polycystic_kidney_disease",
        "dx_categories": ["INDICATION"],
        "module_stems": ["polycystic_kidney_disease"],
        # Tolvaptan is oral; the sheet carries no HCPCS at all.
        "partb_expected": False,
    },
    # ---------------------------------------------------------------- Immunology
    "RA": {
        "name": "Rheumatoid Arthritis",
        "board_area": "Immunology",
        "board_exists": True,
        "board_patients": 61015,
        "sheet": "ai_rheumatoid_arthritis",
        "dx_categories": ["INDICATION"],
        "module_stems": ["rheumatoid_arthritis"],
        "partb_expected": True,
    },
    "SLE": {
        "name": "Systemic Lupus Erythematosus",
        "board_area": "Immunology",
        "board_exists": True,
        "board_patients": 1691,
        "sheet": "ai_sle",
        "dx_categories": ["INDICATION", "LUPUS NEPHRITIS"],
        "module_stems": ["sle", "lupus", "systemic_lupus_erythematosus"],
        "partb_expected": True,
    },
    "CIDP": {
        "name": "Chronic Inflammatory Demyelinating Polyneuropathy",
        "board_area": "Immunology",
        "board_exists": True,
        "board_patients": 1692,
        "sheet": "ai_cidp",
        "dx_categories": ["INDICATION"],
        "module_stems": ["cidp", "chronic_inflammatory_demyelinating_polyneuropathy"],
        # IVIG and SCIG are the whole treatment axis, and both are Part B J-codes.
        "partb_expected": True,
    },
    "GMG": {
        "name": "Myasthenia Gravis",
        "board_area": "Immunology",
        "board_exists": True,
        "board_patients": 22,
        "sheet": "gmg",
        # INDICATION is G700/G7000/G7001 only. The sheet's DME_MOBILITY_CLAIM and
        # GENERAL_SYMPTOM_CLAIM categories are deliberately excluded: they are
        # supportive-equipment and symptom codes, and DME_MOBILITY_CLAIM additionally
        # carries HCPCS codes mistyped as ICD-10-CM (see the data-quality cell).
        "dx_categories": ["INDICATION"],
        "module_stems": ["myasthenia_gravis", "gmg"],
        "partb_expected": True,
    },
    "PI": {
        "name": "Primary Immunodeficiency",
        "board_area": "Immunology",
        "board_exists": True,
        "board_patients": 22443,
        "sheet": "ai_primary_immunodeficiency",
        "dx_categories": ["INDICATION"],
        "module_stems": ["primary_immunodeficiency"],
        "partb_expected": True,
    },
    # ---------------------------------------------------------------- Infectious disease
    "COVID": {
        "name": "Coronavirus (COVID-19)",
        "board_area": "Infectious Disease",
        "board_exists": True,
        "board_patients": 8102,
        "sheet": "covid19",
        # INDICATION also holds a POST_ACUTE subcategory (M3581, Z8616); restricted to
        # the acute and post-COVID U-codes so history-of codes cannot inflate the cohort.
        "dx_categories": ["INDICATION"],
        "dx_restrict": ["U07", "U09"],
        "module_stems": ["covid19"],
        "partb_expected": False,
    },
    "PNEUMO": {
        "name": "Pneumococcal Pneumonia",
        "board_area": "Infectious Disease",
        "board_exists": True,
        "board_patients": 7012,
        "sheet": "ai_pneumococcal_pneumonia",
        # INDICATION is J13 alone; INVASIVE DISEASE adds pneumococcal sepsis and
        # meningitis, which are the same organism and worth counting.
        "dx_categories": ["INDICATION", "INVASIVE DISEASE"],
        "module_stems": ["pneumococcal_pneumonia", "pneumonia"],
        # The only HCPCS in the sheet is vaccine administration.
        "partb_expected": False,
    },
    # ---------------------------------------------------------------- Neurology
    "ALZ": {
        "name": "Alzheimers Disease",
        "board_area": "Neurology",
        "board_exists": True,
        "board_patients": 7012,
        "sheet": "ai_alzheimers",
        "dx_categories": ["INDICATION"],
        # Deliberately not "dementia": base Synthea ships a dementia module, and matching
        # it would report Alzheimer's as present on the strength of a different disease.
        "module_stems": ["alzheimers", "alzheimers_disease"],
        # The anti-amyloid mAbs are Part B J-codes; base Synthea models none of them,
        # so a NO PART B verdict here is expected rather than surprising.
        "partb_expected": True,
    },
    "PARK": {
        "name": "Parkinsons Disease",
        "board_area": "Neurology",
        "board_exists": True,
        "board_patients": 1451,
        "sheet": "ai_parkinsons",
        # INDICATION is G20 alone. SECONDARY and ATYPICAL PARKINSONISM are different
        # diseases and are left out of the cohort.
        "dx_categories": ["INDICATION"],
        "module_stems": ["parkinsons", "parkinsons_disease"],
        "partb_expected": False,
    },
}

# Registry module_stems that match no file in the built tree. Corrected here rather
# than in the notebook so this repo's gate is self-contained; the notebook needs the
# same correction (tracked separately).
STEM_FIX = {
    'WAMD':   ['wet_amd'],
    'DR':     ['diabetic_retinopathy_treatment'],
    'DME':    [],  # no module exists -- see Task 10
    'CAD':    ['stable_ischemic_heart_disease', 'myocardial_infarction'],
    'PNEUMO': ['pneumonia'],
    'GMG':    ['myasthenia_gravis'],
    'HF':     ['congestive_heart_failure', 'right_sided_heart_failure',
               'valvular_heart_failure', 'high_output_heart_failure'],
    'AML':    ['acute_myeloid_leukemia'],
    'ALL':    ['acute_lymphoblastic_leukemia'],
    'CIDP':   ['CIDP'],
    'SLE':    ['SLE'],
    'ALZ':    ['alzheimers'],
    'PARK':   ['parkinsons'],
    'PANC':   ['pancreatic_cancer'],
    'PV':     ['polycythemia_vera'],
    'MCL':    ['mantle_cell_lymphoma'],
    'LUNG':   ['lung_cancer'],
    'COLON':  ['colorectal_cancer'],
    'RECTAL': ['colorectal_cancer'],
    # Additional stems found stale during Task 0 harness build (registry named files
    # that do not exist in the built tree; corrected the same way as the block above).
    'ENDOMETRIAL': ['endometrial_cancer'],  # 'uterine_cancer' names no file
    'NSCLC':  ['non_small_cell_lung_cancer'],  # 'nsclc' names no file
    'SCLC':   ['small_cell_lung_cancer'],  # 'sclc' names no file
    'DLBCL':  ['dlbcl'],  # 'diffuse_large_b_cell_lymphoma' names no file
    'FL':     [],  # no follicular lymphoma module exists -- see Task 10
}
for _k, _v in STEM_FIX.items():
    if _k in TA_CONFIG:
        TA_CONFIG[_k]['module_stems'] = _v
