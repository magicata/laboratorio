import streamlit as st
import pdfplumber
import re

st.set_page_config(page_title="Resumen Clínico de Laboratorio", layout="wide")

# -------------------- Helpers --------------------

def extract_text(pdf):
    text = ""
    with pdfplumber.open(pdf) as pdf_file:
        for page in pdf_file.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return text

def find(pattern, text, flags=re.IGNORECASE):
    if not text:
        return None
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None

def extract_orina_section(text):
    """Only parse orina fields from the ORINA COMPLETA section to avoid picking ERITROCITOS from hemogram etc."""
    m = re.search(r"ORINA\s+COMPLETA", text, re.IGNORECASE)
    if not m:
        return None
    start = m.start()
    # End at next major section (another test block) or after a reasonable chunk
    end_match = re.search(
        r"(?:HEMOGLOBINA\s+GLICADA|PERFIL\s+LIPIDICO|CREATININA\s+[\d]|Muestra\s*:\s*SANGRE|Nº\s+Orden)",
        text[start + 100 : start + 4000],
        re.IGNORECASE
    )
    end = start + 100 + (end_match.start() if end_match else 3500)
    return text[start:end]

def abnormal_numeric(val, low=None, high=None):
    v = float(val)
    if low is not None and v < low:
        return True
    if high is not None and v > high:
        return True
    return False

def abnormal_text(val, normal="negativo"):
    return val is not None and val.lower() != normal.lower()

def flag(val, abnormal):
    return f"<span style='color:red'><b>{val}</b></span>" if abnormal else str(val)

def normalize_frotis(text):
    if not text:
        return "Normal"
    if "normal" in text.lower():
        return "Normal"
    return text

def normalize_range(val):
    """Keep range as-is for display (e.g. 0-3, 3-6, >100); collapse spaces around dash."""
    if not val:
        return None
    return re.sub(r"\s*[-–]\s*", "-", val.strip())

def trim_decimal_zero(val):
    """Display value without trailing .0 (e.g. 143.0 -> 143)."""
    if not val:
        return val
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else val
    except ValueError:
        return val

# -------------------- UI --------------------

st.title("🧪 Resumen Clínico de Laboratorio")

riesgo_cv = st.radio(
    "Riesgo Cardiovascular",
    ["Bajo", "Medio", "Alto"],
    horizontal=True
).lower()

uploaded_file = st.file_uploader("Subir informe de laboratorio (PDF)", type=["pdf"])

if uploaded_file:
    text = extract_text(uploaded_file)

    # -------------------- Fecha --------------------

    # Toma (de) Muestra: first date after that label (DD-MM-YYYY or DD/MM/YYYY), output DD/MM/YY
    fecha_raw = find(r"(?:TOMA\s+(?:DE\s+)?MUESTRA|Recep\.?\s*Muestra)[\s\S]*?(\d{2}[-/]\d{2}[-/]\d{4})", text)
    if fecha_raw:
        parts = re.split(r"[-/]", fecha_raw)
        fecha = f"{parts[0]}/{parts[1]}/{parts[2][-2:]}" if len(parts) == 3 else fecha_raw.replace("-", "/")
    else:
        fecha = None

    # -------------------- Patient --------------------

    edad = find(r"Edad\s*:?\s*(\d+)", text)
    edad = int(edad) if edad else None

    sexo_raw = find(r"Sexo\s*:?\s*(FEMENINO|MASCULINO)", text)
    sexo = "mujer" if sexo_raw == "FEMENINO" else "hombre" if sexo_raw else None

    # -------------------- Context --------------------

    TSH_MAX = 3 if edad and edad <= 65 else 6
    LDL_MAX = 70 if riesgo_cv == "alto" else 100 if riesgo_cv == "medio" else 130
    HB_MIN = 13 if sexo == "hombre" else 12 if sexo == "mujer" else None

    # -------------------- Chemistry --------------------

    crea = find(r"CREATININA\s+([\d\.]+)", text)
    vfg = find(r"VFG.*?MDRD.*?([\d]{2,3})", text)
    bun = find(r"NITROGENO UREICO\s+([\d\.]+)", text)
    urea = find(r"UREMIA\s+([\d\.]+)", text)
    au = find(r"ACIDO URICO\s+([\d\.]+)", text)
    rac = find(r"RELACION MICRO.*?([\d\.]+)", text)

    na = find(r"SODIO\s+([\d\.]+)", text)
    k = find(r"POTASIO\s+([\d\.]+)", text)
    cl = find(r"CLORO\s+([\d\.]+)", text)

    glu = find(r"GLUCOSA EN SANGRE\s+([\d\.]+)", text)
    hba1c = find(r"HEMOGLOBINA GLICADA A1C\s+([\d]+(?:\.[\d]+)?)\s*%", text)

    ptgo_basal = find(r"GLICEMIA BASAL\s+([\d\.]+)", text)
    ptgo_120 = find(r"120\s*MIN.*?([\d\.]+)", text)

    tsh = find(r"TSH.*?([\d\.]+)", text)
    t4l = find(r"T4\s*LIBRE.*?([\d\.]+)", text)

    # -------------------- Lipid profile --------------------

    col_total = find(r"COLESTEROL TOTAL\s+([\d\.]+)", text)
    ldl = find(r"(?:LDL|COLESTEROL LDL|C[-\s]?LDL).*?([\d\.]+)", text)
    hdl = find(r"(?:HDL|COLESTEROL HDL|C[-\s]?HDL).*?([\d\.]+)", text)
    tg = find(r"TRIGLICERIDOS\s+([\d\.]+)", text)

    # -------------------- Hemogram --------------------

    hb = find(r"HEMOGLOBINA\s+([\d\.]+)", text)
    hcto = find(r"HEMATOCRITO\s+([\d\.]+)", text)
    vcm = find(r"V\.?C\.?M\.?\s+([\d\.]+)", text)
    chcm = find(r"C\.?H\.?C\.?M\.?\s+([\d\.]+)", text)
    gb = find(r"RECUENTO.*?LEUCOCITOS\s+([\d\.]+)", text, re.DOTALL | re.IGNORECASE)
    plq = find(r"RECUENTO.*?PLAQUETAS\s+([\d\.]+)", text, re.DOTALL | re.IGNORECASE)
    if not plq:
        plq = find(r"PLAQUETAS\s+([\d\.]+)\s*(?:/\s*μL|K|/\s*L|G/L)?", text)
    vhs = find(r"V\.?H\.?S\.?\s+([\d\.]+)", text)

    # -------------------- Orina completa (only if ORINA COMPLETA is in the report) --------------------
    oc_section = extract_orina_section(text)
    if not oc_section:
        oc_gr = oc_gb = oc_bact = oc_nit = oc_bili = oc_prot = oc_glu = None
    else:
        oc_gr = normalize_range(find(
            r"ERITROCITOS\s+(\d+\s*[-–]\s*\d+|[<>]\s*\d+|\d+)",
            oc_section
        ))
        oc_gb = normalize_range(find(
            r"LEUCOCITOS\s*\(MIC\)\s*(\d+\s*[-–]\s*\d+|[<>]\s*\d+|\d+)",
            oc_section
        ))
        oc_bact_raw = find(r"BACTERIAS\s+([^\t\n]+)", oc_section)
        if oc_bact_raw:
            oc_bact = re.sub(r"\s+No se Observan\s*$", "", oc_bact_raw.strip(), flags=re.IGNORECASE).strip()
        else:
            oc_bact = None
        oc_nit = find(r"NITRITOS\s+(POSITIVO|NEGATIVO)", oc_section)
        oc_bili = find(r"BILIRRUBINA\s+(POSITIVO|NEGATIVO)", oc_section)
        oc_prot = find(r"PROTEINAS\s+(POSITIVO|NEGATIVO)", oc_section)
        oc_glu = find(r"GLUCOSA\s+(POSITIVO|NEGATIVO)", oc_section)

    # -------------------- Morphology / Frotis --------------------
    # MORFOLOGIA SERIE ROJA, MORFOLOGIA SERIE BLANCA, MORFOLOGIA DE PLAQUETAS (or PLAQUETARIA)
    # Try same-line value first, then multiline (value on next line)
    def trim_morph(val):
        """First line only; remove trailing reference text (e.g. 'No se observan', 'x campo')."""
        if not val:
            return None
        first = val.strip().split("\n")[0].strip()
        first = re.sub(r"\s+(?:No se observan?|x campo).*$", "", first, flags=re.IGNORECASE).strip()
        return first or None

    def extract_morph(pattern_same_line, pattern_multiline, text):
        val = find(pattern_same_line, text)
        if val:
            return trim_morph(val)
        val = find(pattern_multiline, text)
        if val:
            return trim_morph(val)
        return None

    _morph_tail = r"(?=\n|\r|MORFOLOG|HEMOGLOBINA|CREATININA|V\.?C\.?M\.?|$)"
    morph_roja = extract_morph(
        r"MORFOLOG[IÍ]A\s+SERIE\s+ROJA\s*[:\s]+([^\n\r]+)" + _morph_tail,
        r"MORFOLOG[IÍ]A\s+SERIE\s+ROJA\s+([\s\S]+?)" + _morph_tail,
        text
    )
    morph_blanca = extract_morph(
        r"MORFOLOG[IÍ]A\s+SERIE\s+BLANCA\s*[:\s]+([^\n\r]+)" + _morph_tail,
        r"MORFOLOG[IÍ]A\s+SERIE\s+BLANCA\s+([\s\S]+?)" + _morph_tail,
        text
    )
    # MORFOLOGIA DE PLAQUETAS or MORFOLOGIA PLAQUETARIA
    morph_plaq = extract_morph(
        r"MORFOLOG[IÍ]A\s+(?:DE\s+)?PLAQUETAS?\s*[:\s]+([^\n\r]+)" + _morph_tail,
        r"MORFOLOG[IÍ]A\s+(?:DE\s+PLAQUETAS|PLAQUETARIA)\s+([\s\S]+?)" + _morph_tail,
        text
    )
    if not morph_plaq:
        morph_plaq = extract_morph(
            r"MORFOLOG[IÍ]A\s+PLAQUETARIA\s*[:\s]+([^\n\r]+)" + _morph_tail,
            r"MORFOLOG[IÍ]A\s+PLAQUETARIA\s+([\s\S]+?)" + _morph_tail,
            text
        )

    hemogram_present = any([hb, hcto, gb, plq, vhs, morph_roja, morph_blanca, morph_plaq])

    def is_normal(val):
        return val and val.strip().lower() == "normales"

    # Frotis: "Normal" only if all three are "Normales"; otherwise abnormal result(s) with section prefix (GR, GB, PLQ)
    frotis_parts = []
    if morph_roja and not is_normal(morph_roja):
        frotis_parts.append(f"GR {morph_roja}")
    if morph_blanca and not is_normal(morph_blanca):
        frotis_parts.append(f"GB {morph_blanca}")
    if morph_plaq and not is_normal(morph_plaq):
        frotis_parts.append(f"PLQ {morph_plaq}")

    if morph_roja is not None and morph_blanca is not None and morph_plaq is not None:
        if is_normal(morph_roja) and is_normal(morph_blanca) and is_normal(morph_plaq):
            frotis = "Normal"
        elif frotis_parts:
            frotis = "; ".join(frotis_parts)
        else:
            frotis = "Normal"
    elif frotis_parts:
        frotis = "; ".join(frotis_parts)
    else:
        frotis = None


    # -------------------- Output --------------------

    html, text_out = [], []

    def add(h, t):
        if h.strip():
            html.append(h)
            text_out.append(t)

    # -------- Renal --------

    renal_h, renal_t = [], []
    if crea: renal_h.append(f"Crea {crea}"); renal_t.append(f"Crea {crea}")
    if vfg: renal_h.append(f"VFG {flag(vfg, abnormal_numeric(vfg, low=60))}"); renal_t.append(f"VFG {vfg}")
    if bun: renal_h.append(f"BUN {flag(bun, abnormal_numeric(bun,8,25))}"); renal_t.append(f"BUN {bun}")
    if urea: renal_h.append(f"Urea {flag(urea, abnormal_numeric(urea,21,49))}"); renal_t.append(f"Urea {urea}")
    if au: renal_h.append(f"AU {flag(au, abnormal_numeric(au,2.3,6.1))}"); renal_t.append(f"AU {au}")

    if na and k and cl:
        na_d, k_d, cl_d = trim_decimal_zero(na), trim_decimal_zero(k), trim_decimal_zero(cl)
        renal_h.append(f"ELP {flag(na_d, abnormal_numeric(na,135,145))}/{flag(k_d, abnormal_numeric(k,3.5,5))}/{flag(cl_d, abnormal_numeric(cl,98,107))}")
        renal_t.append(f"ELP {na_d}/{k_d}/{cl_d}")

    if rac:
        renal_h.append(f"RAC {flag(rac, abnormal_numeric(rac, high=30))}")
        renal_t.append(f"RAC {rac}")

    add(" ".join(renal_h), " ".join(renal_t))

    # -------- Orina --------

    oc_h, oc_t = [], []
    if oc_gr:
        oc_h.append(f"GR {flag(oc_gr, oc_gr not in ['0-3', '<3'])}")
        oc_t.append(f"GR {oc_gr}")
    if oc_gb:
        oc_h.append(f"GB {flag(oc_gb, oc_gb not in ['0-3', '<3'])}")
        oc_t.append(f"GB {oc_gb}")
    if oc_bact: oc_h.append(f"Bacterias {oc_bact}"); oc_t.append(f"Bacterias {oc_bact}")
    if oc_nit: oc_h.append(f"Nitritos {flag(oc_nit, abnormal_text(oc_nit))}"); oc_t.append(f"Nitritos {oc_nit}")
    if oc_bili == "POSITIVO": oc_h.append(f"Bilirrubina {flag('POSITIVO',True)}"); oc_t.append("Bilirrubina POSITIVO")
    if oc_prot: oc_h.append(f"Proteinas {flag(oc_prot, abnormal_text(oc_prot))}"); oc_t.append(f"Proteinas {oc_prot}")
    if oc_glu: oc_h.append(f"Glucosa {flag(oc_glu, abnormal_text(oc_glu))}"); oc_t.append(f"Glucosa {oc_glu}")

    if oc_h:
        add("OC " + " ".join(oc_h), "OC " + " ".join(oc_t))

    # -------- Metabolic --------

    meta_h, meta_t = [], []
    if glu: meta_h.append(f"Glu {flag(glu, abnormal_numeric(glu,70,100))}"); meta_t.append(f"Glu {glu}")
    if hba1c: meta_h.append(f"HbA1c {flag(hba1c+'%', abnormal_numeric(hba1c,4,6))}"); meta_t.append(f"HbA1c {hba1c}%")
    if ptgo_basal and ptgo_120:
        meta_h.append(f"PTGO {flag(ptgo_basal, abnormal_numeric(ptgo_basal,70,100))}/{flag(ptgo_120, abnormal_numeric(ptgo_120, high=140))}")
        meta_t.append(f"PTGO {ptgo_basal}/{ptgo_120}")
    if tsh: meta_h.append(f"TSH {flag(tsh, abnormal_numeric(tsh, high=TSH_MAX))}"); meta_t.append(f"TSH {tsh}")
    if t4l: meta_h.append(f"T4L {t4l}"); meta_t.append(f"T4L {t4l}")

    if meta_h:
        add(" ".join(meta_h), " ".join(meta_t))

    # -------- Hemogram (before Lipids) --------

    # Hemogram reference: GB 4.5–11, PLQ 150–450, VHS men & women <50: <20; women ≥50: <30
    if hemogram_present:
        hemo_h, hemo_t = [], []
        hb_abn = hb and float(hb) < HB_MIN
        if hb: hemo_h.append(f"Hb {flag(hb, hb_abn)}"); hemo_t.append(f"Hb {hb}")
        if hb_abn:
            if vcm: hemo_h.append(f"VCM {vcm}"); hemo_t.append(f"VCM {vcm}")
            if chcm: hemo_h.append(f"CHCM {chcm}"); hemo_t.append(f"CHCM {chcm}")
        if hcto: hemo_h.append(f"Hcto {hcto}"); hemo_t.append(f"Hcto {hcto}")
        if gb:
            gb_val = int(float(gb) * 1000)
            gb_abn = float(gb) < 4.5 or float(gb) > 11
            hemo_h.append(f"GB {flag(gb_val, gb_abn)}")
            hemo_t.append(f"GB {gb_val}")
        if plq:
            plq_abn = float(plq) < 150 or float(plq) > 450
            hemo_h.append(f"PLQ {flag(plq, plq_abn)}K")
            hemo_t.append(f"PLQ {plq}K")
        if vhs:
            vhs_max = 30 if (sexo == "mujer" and edad is not None and edad >= 50) else 20
            vhs_abn = float(vhs) >= vhs_max
            hemo_h.append(f"VHS {flag(vhs, vhs_abn)}")
            hemo_t.append(f"VHS {vhs}")
        if frotis:
            hemo_h.append(f"Frotis {flag(frotis, frotis != 'Normal')}")
            hemo_t.append(f"Frotis {frotis}")

        add(" ".join(hemo_h), " ".join(hemo_t))

    # -------- Lipids --------

    lip_h, lip_t = [], []

    if col_total:
        lip_h.append(f"CT {flag(col_total, abnormal_numeric(col_total, high=200))}")
        lip_t.append(f"CT {col_total}")

    if ldl:
        lip_h.append(f"LDL {flag(ldl, abnormal_numeric(ldl, high=LDL_MAX))}")
        lip_t.append(f"LDL {ldl}")

    if hdl:
        HDL_MIN = 50 if sexo == "mujer" else 40
        lip_h.append(f"HDL {flag(hdl, abnormal_numeric(hdl, low=HDL_MIN))}")
        lip_t.append(f"HDL {hdl}")

    if tg:
        lip_h.append(f"TG {flag(tg, abnormal_numeric(tg, high=150))}")
        lip_t.append(f"TG {tg}")

    if lip_h:
        add(" ".join(lip_h), " ".join(lip_t))

    # Prepend date (DD/MM/YY) to first line of output when present
    if fecha and html:
        html[0] = f"<b>{fecha}:</b> " + html[0]
    if fecha and text_out:
        text_out[0] = f"{fecha}: " + text_out[0]

    # -------------------- Display --------------------

    st.markdown("<hr>", unsafe_allow_html=True)
    for line in html:
        st.markdown(line, unsafe_allow_html=True)

    st.text_area("📋 Copiar resultado", "\n".join(text_out), height=240)

