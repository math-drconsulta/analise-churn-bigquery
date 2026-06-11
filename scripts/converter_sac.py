import pandas as pd

xls = pd.ExcelFile("results/SAC YALO & DRC.xlsx")
for sheet in xls.sheet_names:
    full = pd.read_excel(xls, sheet_name=sheet)
    print(f"{sheet}: {len(full)} linhas, {len(full.columns)} colunas")
    print(list(full.columns))
    print(full.head(3).to_string(max_colwidth=60))
    safe = sheet.replace(" ", "_").replace("&", "e")
    full.to_csv(f"results/sac_{safe}.csv", index=False)
    print(f"-> results/sac_{safe}.csv")
    print()
