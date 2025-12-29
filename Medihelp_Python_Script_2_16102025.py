# -*- coding: utf-8 -*-
"""
Created on Wed Oct 15 17:54:36 2025

@author: mdesambath
"""
##---------------------------------------------------------
##Step2  Read ddls and read flatfiles read tables and output and table match and assign 
## header details and delimit the data with "|"
## Author De. Sambath Margabandhu (Lead Architect) Mphatek Systems
## Script prepared and used only within Medihelp environment
##------------------------------------------------------
########################################################
#### Step 2 final step to generate the files from SQL
##### very important program which creates formatted text file
## Generates output files as *_Formatted.txt 
## uses program0 expanded.sql which is an important source 
## any new additions/changes to the file names or tables should be updated in File_Table_Mapping file
## this is the control file based on which the file looks at it and generates tout output file
## layout files are generated just to cross check whether it provides the same structure as copybook
## the paths can be set based on the requirements
## the existing path is primarily based on the development
## the layout path can be specified separately to generate the layout files currently it gets generated inside output file
######### Final program with all fixes done
##15-10 DelimiterChanges done and its working fine
## 15-10 output name changed back to the source file name as per the project team's needs
## important libraries to be loaded without which the program will not run


import os
import re
import pandas as pd
from collections import defaultdict

######################
# -------------------
# File paths
# -------------------
ddl_file = "/home/dostotest/Medihelp/Payal 1/Payal/Design/SQLoutput/program0_expanded.sql"
mapping_file = "/home/dostotest/Medihelp/Payal 1/Payal/File_Table_Mapping.csv"
data_folder = "/home/dostotest/Medihelp/Payal 1/Payal/Files/Data/kiran"
output_folder = "/home/dostotest/Medihelp/Payal 1/Payal/Files/Processed/output/kiran"
layout_folder = os.path.join(output_folder, "Layout")

os.makedirs(output_folder, exist_ok=True)
os.makedirs(layout_folder, exist_ok=True)

FIELD_DELIM = "¦"   # replaces '|'
GROUP_DELIM = "§"   # replaces '~'

# -------------------
# Helpers
# -------------------
def normalize_name(name: str) -> str:
    parts = re.split(r"[_\-]", name.strip('"').upper())
    return "".join(p.capitalize() for p in parts if p)

def normalize_column(name: str) -> str:
    return name.replace("_", "").replace("-", "").upper()

# -------------------
# Load mapping file
# -------------------
try:
    df = pd.read_csv(mapping_file, encoding="utf-8")
except UnicodeDecodeError:
    df = pd.read_csv(mapping_file, encoding="latin-1")

df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_").str.replace("-", "_")

if not {"table_name", "flat_file_name"}.issubset(df.columns):
    raise ValueError(f"CSV must contain table_name and flat_file_name columns, found: {df.columns.tolist()}")

# -------------------
# Parse CREATE TABLE DDLs
# -------------------
def parse_ddl(ddl_text):
    tables = {}
    current_table = None
    pos = 1

    for line in ddl_text.splitlines():
        line = line.strip()
        m = re.match(r"CREATE TABLE\s+(?:\w+\.)?([\"\w\-#]+)", line, re.IGNORECASE)
        if m:
            current_table = m.group(1).strip('"').upper().replace("-", "_")
            tables[current_table] = []
            pos = 1
            continue

        if current_table and line and not line.startswith(");"):
            col_match = re.match(r"([\"\w#-]+)\s+VARCHAR\((\d+)\)", line.rstrip(","), re.IGNORECASE)
            if col_match:
                col_name = normalize_column(col_match.group(1).strip('"'))
                width = int(col_match.group(2))
                start, end = pos, pos + width - 1
                tables[current_table].append((col_name, f"VARCHAR({width})", width, start, end))
                pos = end + 1

    return tables

with open(ddl_file, "r", encoding="latin-1") as f:
    ddl_text = f.read()

tables = parse_ddl(ddl_text)

# -------------------
# Process tables
# -------------------
for idx, row in df.iterrows():
    raw_table = str(row["table_name"]).strip()
    table = raw_table.upper().replace("-", "_")
    flat_file = row["flat_file_name"]

    if not table or pd.isna(table):
        print(f"Skipping: Blank table name for file {flat_file}")
        continue

    if table not in tables:
        print(f" Table {table} not found in DDL, skipping…")
        continue

    input_path = os.path.join(data_folder, flat_file)
    if not os.path.exists(input_path):
        print(f" Data file {input_path} not found, skipping…")
        continue

    # Generate normalized output file name from flat file name (no extension)
    ##seq_prefix = f"{idx+1:03d}_"
    flatfile_base = os.path.splitext(os.path.basename(flat_file))[0]
    flatfile_norm = normalize_name(flatfile_base).upper()
    output_path = os.path.join(output_folder, f"{flatfile_norm}.TXT")
    layout_path = os.path.join(layout_folder, f"{flatfile_norm}.TXT")
    fields = tables[table]
    max_end = max(end for _, _, _, _, end in fields)

    # -------------------
    # Detect repeating groups
    # -------------------
    grouped_fields = defaultdict(list)
    for col_name, col_type, width, start, end in fields:
        m = re.match(r"([A-Z_]+?)(\d+)$", col_name)
        if m:
            base = m.group(1)
            grouped_fields[base].append((col_name, col_type, width, start, end))
        else:
            grouped_fields[col_name].append((col_name, col_type, width, start, end))

    # Maintain original order
    ordered_groups = []
    seen = set()
    for col_name, _, _, _, _ in fields:
        m = re.match(r"([A-Z_]+?)(\d+)$", col_name)
        base = m.group(1) if m else col_name
        if base not in seen:
            ordered_groups.append(base)
            seen.add(base)

    # -------------------
    # Prepare grouped header names (with _PE for repeated)
    # -------------------
    display_headers = []
    for base in ordered_groups:
        cols = grouped_fields[base]
        if len(cols) > 1:
            display_headers.append(f"{base}_PE")
        else:
            display_headers.append(base)

    # -------------------
    # Write layout file
    # -------------------
    with open(layout_path, "w", encoding="utf-8") as f_layout:
        f_layout.write(FIELD_DELIM.join(["FieldName", "DataType", "Start", "End", "Width"]) + "\n")
        #f_layout.write("FieldName|DataType|Start|End|Width\n")
        for base in ordered_groups:
            cols = grouped_fields[base]
            if len(cols) == 1:
                col_name, col_type, width, start, end = cols[0]
                #f_layout.write(f"{base}|{col_type}|{start}|{end}|{width}\n")
                f_layout.write(FIELD_DELIM.join([base, col_type, str(start), str(end), str(width)]) + "\n")
            else:
                total_width = sum(c[2] for c in cols)
                start = cols[0][3]
                end = cols[-1][4]
                base_type = cols[0][1]
                #f_layout.write(f"{base}_PE|{base_type}|{start}|{end}|{total_width}\n")
                f_layout.write(FIELD_DELIM.join([f"{base}_PE", base_type, str(start), str(end), str(total_width)]) + "\n")
    # -------------------
    # Write formatted output file
    # -------------------
    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, open(output_path, "w", encoding="utf-8") as fout:
        #fout.write("|".join(display_headers) + "\n")
        fout.write(FIELD_DELIM.join(display_headers) + "\n")
        for record in fin:
            record = record.rstrip("\r\n")
            if len(record) < max_end:
                record = record.ljust(max_end)
            row_values = []
            for base in ordered_groups:
                cols = grouped_fields[base]
                if len(cols) == 1:
                    col_name, col_type, width, start, end = cols[0]
                    raw_val = record[start-1:end].strip()
                    row_values.append(raw_val)
                    
                else:
                    group_vals = []
                    for col_name, col_type, width, start, end in cols:
                        val = record[start-1:end].strip()
                        group_vals.append(val)
                    #row_values.append("~".join(group_vals))
                    row_values.append(GROUP_DELIM.join(group_vals))
            #fout.write("|".join(row_values) + "\n")
            fout.write(FIELD_DELIM.join(row_values) + "\n")

    print(f" {table}: Processed")
    print(f"   → Output: {output_path}")
    print(f"   → Layout: {layout_path}")