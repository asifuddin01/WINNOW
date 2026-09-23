"""Common evidence sources offered as suggestions to future adapters and interfaces."""

# This is deliberately not an allow-list. Reviewed 2026-09-23 against the Cochrane Handbook,
# Gusenbauer and Haddaway's 2020 search-system study, and the current WHO registry network.
# It combines common sources with major specialist/regional indexes; projects may use any name.
COMMON_DATABASES: tuple[str, ...] = (
    "ACM Digital Library",
    "African Index Medicus",
    "AGRICOLA",
    "Allied and Complementary Medicine Database (AMED)",
    "APA PsycINFO",
    "arXiv",
    "BASE (Bielefeld Academic Search Engine)",
    "bioRxiv",
    "BIOSIS Previews",
    "Business Source Complete",
    "CAB Abstracts",
    "CINAHL",
    "CiNii Research",
    "CNKI",
    "Cochrane CENTRAL",
    "DBLP",
    "Directory of Open Access Journals (DOAJ)",
    "EconLit",
    "Embase",
    "Epistemonikos",
    "ERIC",
    "Global Health (CABI)",
    "Google Scholar",
    "IEEE Xplore",
    "Ichushi-Web",
    "IndMED",
    "Inspec",
    "International Pharmaceutical Abstracts",
    "JSTOR",
    "KoreaMed",
    "LILACS",
    "MEDLINE",
    "medRxiv",
    "OpenAlex",
    "PEDro",
    "ProQuest Dissertations & Theses Global",
    "PubMed",
    "SciELO",
    "ScienceDirect",
    "Scopus",
    "Semantic Scholar",
    "SinoMed",
    "Social Science Citation Index",
    "Sociological Abstracts",
    "SPORTDiscus",
    "SSRN",
    "TRID",
    "Trip medical database",
    "Wanfang Data",
    "Web of Science Core Collection",
    "WHO Global Index Medicus",
    "WorldCat",
)

# ClinicalTrials.gov is included alongside the current WHO primary-registry network because
# it is a core evidence source even though WHO classifies it separately as a data provider.
COMMON_TRIAL_REGISTRIES: tuple[str, ...] = (
    "Australian New Zealand Clinical Trials Registry (ANZCTR)",
    "Brazilian Clinical Trials Registry (ReBec)",
    "Chinese Clinical Trial Registry (ChiCTR)",
    "Clinical Research Information Service (CRiS)",
    "Clinical Trials Information System (CTIS)",
    "Clinical Trials Registry - India (CTRI)",
    "ClinicalTrials.gov",
    "Cuban Public Registry of Clinical Trials (RPCEC)",
    "EU Clinical Trials Register (EU-CTR)",
    "German Clinical Trials Register (DRKS)",
    "International Traditional Medicine Clinical Trial Registry (ITMCTR)",
    "Iranian Registry of Clinical Trials (IRCT)",
    "ISRCTN Registry",
    "Japan Registry of Clinical Trials (jRCT)",
    "Lebanese Clinical Trials Registry (LBCTR)",
    "Pan African Clinical Trial Registry (PACTR)",
    "Peruvian Clinical Trial Registry (REPEC)",
    "Sri Lanka Clinical Trials Registry (SLCTR)",
    "Thai Clinical Trials Registry (TCTR)",
)

COMMON_SEARCH_PORTALS: tuple[str, ...] = (
    "WHO International Clinical Trials Registry Platform (ICTRP)",
)

COMMON_EVIDENCE_SOURCES: tuple[str, ...] = (
    COMMON_DATABASES + COMMON_TRIAL_REGISTRIES + COMMON_SEARCH_PORTALS
)
