INDEX_URLS = {
    "NIFTY50": "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "NIFTY100": "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    "NIFTY200": "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
    "NIFTY500": "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
}

SECTOR_PAGES = {
    "NIFTY_AUTO": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-auto",
    "NIFTY_BANK": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank",
    "NIFTY_CEMENT": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-cement",
    "NIFTY_CHEMICALS": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-chemicals",
    "NIFTY_FINANCIAL_SERVICES": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-financial-services",
    "NIFTY_FINANCIAL_SERVICES_25_50": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-financial-services-25-50-index",
    "NIFTY_FINANCIAL_SERVICES_EX_BANK": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-financial-services-ex-bank",
    "NIFTY_FMCG": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-fmcg",
    "NIFTY_HEALTHCARE": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-healthcare-index",
    "NIFTY_IT": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-it",
    "NIFTY_MEDIA": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-media",
    "NIFTY_METAL": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-metal",
    "NIFTY_PHARMA": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-pharma",
    "NIFTY_PRIVATE_BANK": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-private-bank",
    "NIFTY_PSU_BANK": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-psu-bank",
    "NIFTY_REALTY": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-realty",
    "NIFTY_REITS_REALTY": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-reits-realty",
    "NIFTY_CONSUMER_DURABLES": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-consumer-durables-index",
    "NIFTY_OIL_AND_GAS": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-oil-and-gas-index",
}

SECTOR_CSV_URLS = {
    "NIFTY_AUTO": "https://www.niftyindices.com/IndexConstituent/ind_niftyautolist.csv",
    "NIFTY_BANK": "https://www.niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
    "NIFTY_CEMENT": "https://www.niftyindices.com/IndexConstituent/ind_NiftyCement_list.csv",
    "NIFTY_CHEMICALS": "https://www.niftyindices.com/IndexConstituent/ind_niftyChemicals_list.csv",
    "NIFTY_FINANCIAL_SERVICES": "https://www.niftyindices.com/IndexConstituent/ind_niftyfinancelist.csv",
    "NIFTY_FINANCIAL_SERVICES_25_50": "https://www.niftyindices.com/IndexConstituent/ind_niftyfinancialservices25-50list.csv",
    "NIFTY_FINANCIAL_SERVICES_EX_BANK": "https://www.niftyindices.com/IndexConstituent/ind_niftyfinancialservicesexbank_list.csv",
    "NIFTY_FMCG": "https://www.niftyindices.com/IndexConstituent/ind_niftyfmcglist.csv",
    "NIFTY_HEALTHCARE": "https://www.niftyindices.com/IndexConstituent/ind_niftyhealthcarelist.csv",
    "NIFTY_IT": "https://www.niftyindices.com/IndexConstituent/ind_niftyitlist.csv",
    "NIFTY_MEDIA": "https://www.niftyindices.com/IndexConstituent/ind_niftymedialist.csv",
    "NIFTY_METAL": "https://www.niftyindices.com/IndexConstituent/ind_niftymetallist.csv",
    "NIFTY_PHARMA": "https://www.niftyindices.com/IndexConstituent/ind_niftypharmalist.csv",
    "NIFTY_PRIVATE_BANK": "https://www.niftyindices.com/IndexConstituent/ind_nifty_privatebanklist.csv",
    "NIFTY_PSU_BANK": "https://www.niftyindices.com/IndexConstituent/ind_niftypsubanklist.csv",
    "NIFTY_REALTY": "https://www.niftyindices.com/IndexConstituent/ind_niftyrealtylist.csv",
    "NIFTY_CONSUMER_DURABLES": "https://www.niftyindices.com/IndexConstituent/ind_niftyconsumerdurableslist.csv",
    "NIFTY_OIL_AND_GAS": "https://www.niftyindices.com/IndexConstituent/ind_niftyoilgaslist.csv",
}

SECTOR_FALLBACK_SYMBOLS = {
    "NIFTY_REITS_REALTY": [
        "NSE:EMBASSY-EQ",
        "NSE:BROOKFIELD-EQ",
        "NSE:NEXUSSELECT-EQ",
        "NSE:KRT-EQ",
        "NSE:MINDSPACE-EQ",
        "NSE:DLF-EQ",
        "NSE:PHOENIXLTD-EQ",
        "NSE:GODREJPROP-EQ",
        "NSE:LODHA-EQ",
        "NSE:PRESTIGE-EQ",
        "NSE:OBEROIRLTY-EQ",
        "NSE:BRIGADE-EQ",
        "NSE:ANANTRAJ-EQ",
        "NSE:SOBHA-EQ",
        "NSE:SIGNATURE-EQ",
    ],
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.niftyindices.com/",
    "Accept": "text/csv,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 30