##---------------------------------------------------------
##Step1 data structure conversion using Copybook files
## Author De.Sambath Margabandhu (Lead Architect) Mphatek Systems
## Script prepared and used only within Medihelp environment
##------------------------------------------------------
########################################################
## Step 1 of the script
## This script generates the file and converts it into sql readable format from Copybook
## This also eliminates few conditions such as 02 with no width would be ignored
## segregates all PE files and creates branches accordingly
## working script - 26-Sept 2025
# STEP! final — skip ONLY 02s with no type/width and their 03 children
# FIXED: Table names keep underscores, only replace '-' with '_'
############################################


import re
import os
def parse_cobol_type(cobol_type: str) -> str:
    """Convert COBOL type (A, N, Nn.m) into VARCHAR(length)."""
    cobol_type = (cobol_type or "").strip()
    m = re.match(r'N(\d+)\.(\d+)', cobol_type)  # decimal numbers like N7.2
    if m:
        return f"VARCHAR({int(m.group(1)) + int(m.group(2))})"
    m = re.match(r'([AN])(\d+)', cobol_type)  # simple A12 or N10
    if m:
        return f"VARCHAR({int(m.group(2))})"
    return "VARCHAR(255)"

def get_width(ctype: str) -> int:
    """Extract width from COBOL type."""
    ctype = (ctype or "").strip()
    m = re.match(r'N(\d+)\.(\d+)', ctype)
    if m:
        return int(m.group(1)) + int(m.group(2))
    m = re.match(r'[AN](\d+)', ctype)
    if m:
        return int(m.group(1))
    return 1

def clean_col_name(name: str) -> str:
    """For column names: remove '-' and '_' completely."""
    return re.sub(r'[-_]', '', name)

def clean_table_name(name: str) -> str:
    """For table names: replace '-' with '_', keep existing underscores."""
    return name.replace("-", "_")

def expand_fields(lines, start_pos=1):
    """Expand PE groups, repeat counts, skip invalid 02 + its 03 children."""
    fields = []
    pos = start_pos
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r'^(0[23])\s+([#\w-]+)\s*\(([^)]*)\)', line)

        if m:
            level, name, ctype = m.groups()
            name = clean_col_name(name)
            ctype = (ctype or "").strip()

            # Skip 02 with no type and its 03 children
            if level == "02" and (ctype == "" or ctype.startswith("/*")):
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("03 "):
                    j += 1
                i = j
                continue

            if "/" in ctype and not name.endswith("PE"):
                base_type, repeat = ctype.split("/", 1)
                repeat = int(repeat.strip() or "1")
                width = get_width(base_type)
                sql_type = parse_cobol_type(base_type)
                for r in range(1, repeat + 1):
                    start, end = pos, pos + width - 1
                    fields.append((f"{name}{r}", sql_type, width, start, end))
                    pos = end + 1

            elif name.endswith("PE") and ctype.isdigit():
                repeat = int(ctype)
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].strip()
                    if nxt.startswith("02 ") or nxt.startswith("01 "):
                        break
                    sm = re.match(r'^03\s+([#\w-]+)\s*\(([^)]*)\)', nxt)
                    if sm:
                        sub_name, sub_type = sm.groups()
                        sub_name = clean_col_name(sub_name)
                        sub_type = (sub_type or "").strip()
                        if "/" in sub_type:
                            base_type, sub_repeat = sub_type.split("/", 1)
                            sub_repeat = int(sub_repeat.strip() or "1")
                            width = get_width(base_type)
                            sql_type = parse_cobol_type(base_type)
                            for p in range(1, repeat * sub_repeat + 1):
                                start, end = pos, pos + width - 1
                                fields.append((f"{sub_name}{p}", sql_type, width, start, end))
                                pos = end + 1
                        else:
                            width = get_width(sub_type)
                            sql_type = parse_cobol_type(sub_type)
                            for p in range(1, repeat + 1):
                                start, end = pos, pos + width - 1
                                fields.append((f"{sub_name}{p}", sql_type, width, start, end))
                                pos = end + 1
                    j += 1
                i = j
                continue

            else:
                width = get_width(ctype)
                sql_type = parse_cobol_type(ctype)
                start, end = pos, pos + width - 1
                fields.append((name, sql_type, width, start, end))
                pos = end + 1

        else:
            if line.startswith("02 "):
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("03 "):
                    j += 1
                i = j
                continue

        i += 1
    return fields, pos

def simple_fields(lines, start_pos=1):
    """Simpler parser with skip logic for invalid 02."""
    fields = []
    pos = start_pos
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r'^(0[23])\s+([#\w-]+)\s*\(([^)]*)\)', line)
        if m:
            level, name, ctype = m.groups()
            name = clean_col_name(name)
            ctype = (ctype or "").strip()

            if level == "02" and (ctype == "" or ctype.startswith("/*")):
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("03 "):
                    j += 1
                i = j
                continue

            width = get_width(ctype)
            sql_type = parse_cobol_type(ctype)
            start, end = pos, pos + width - 1
            fields.append((name, sql_type, width, start, end))
            pos = end + 1
        else:
            if line.startswith("02 "):
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("03 "):
                    j += 1
                i = j
                continue
        i += 1
    return fields, pos

def copybook_to_ddls(copybook_text):
    lines = copybook_text.splitlines()
    expanded, direct = [], []
    table_name, table_lines, pos = None, [], 1

    for line in lines:
        line_stripped = line.strip()
        m = re.match(r'^01\s+([#\w-]+)', line_stripped)
        if m:
            if table_name and table_lines:
                raw_text = " ".join(table_lines)
                if "-PE" in raw_text or "/" in raw_text:
                    fields, pos = expand_fields(table_lines, start_pos=1)
                    expanded.append((table_name, fields))
                else:
                    fields, pos = simple_fields(table_lines, start_pos=1)
                    direct.append((table_name, fields))
            table_name = clean_table_name(m.group(1))
            table_lines, pos = [], 1
            continue

        if (line_stripped.startswith("TOTAL RECORD LENGTH") or
            line_stripped.startswith("UNIQUE KEY") or
            line_stripped.startswith("---")):
            if table_name and table_lines:
                raw_text = " ".join(table_lines)
                if "-PE" in raw_text or "/" in raw_text:
                    fields, pos = expand_fields(table_lines, start_pos=1)
                    expanded.append((table_name, fields))
                else:
                    fields, pos = simple_fields(table_lines, start_pos=1)
                    direct.append((table_name, fields))
                table_name, table_lines = None, []
            continue

        if table_name:
            table_lines.append(line)

    if table_name and table_lines:
        raw_text = " ".join(table_lines)
        if "-PE" in raw_text or "/" in raw_text:
            fields, pos = expand_fields(table_lines, start_pos=1)
            expanded.append((table_name, fields))
        else:
            fields, pos = simple_fields(table_lines, start_pos=1)
            direct.append((table_name, fields))

    return expanded, direct

# --------------------------
# Main scriptD:D:\Python_Source_Deliverable\Design\copybooks\L20250830_1_copy.txt
# --------------------------
if __name__ == "__main__":
    input_file = "/home/dostotest/Medihelp/Payal 1/Payal/Design/copybooks/L20251209.txt"
    expanded_sql = "/home/dostotest/Medihelp/Payal 1/Payal/Design/SQLoutput/program0_expanded.sql"
    direct_sql   = "/home/dostotest/Medihelp/Payal 1/Payal/Design/SQLoutput/program0_direct.sql"
    expanded_meta = "/home/dostotest/Medihelp/Payal 1/Payal/Design/SQLoutput/program0_expanded_metadata.txt"
    direct_meta   = "/home/dostotest/Medihelp/Payal 1/Payal/Design/SQLoutput/program0_direct_metadata.txt"

    os.makedirs(os.path.dirname(expanded_sql), exist_ok=True)

    with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
        copybook = f.read()

    expanded, direct = copybook_to_ddls(copybook)

    with open(expanded_sql, "w", encoding="utf-8") as f_sql, open(expanded_meta, "w", encoding="utf-8") as f_meta:
        for tname, fields in expanded:
            f_sql.write(f"CREATE TABLE {tname} (\n    " +
                        ",\n    ".join([f"{fld[0]} {fld[1]}" for fld in fields]) +
                        "\n);\n\n")
            f_meta.write(f"#TABLE {tname}\nFieldName|DataType|Start|End|Width\n")
            for fld in fields:
                f_meta.write(f"{fld[0]}|{fld[1]}|{fld[3]}|{fld[4]}|{fld[2]}\n")
            f_meta.write("\n")

    with open(direct_sql, "w", encoding="utf-8") as f_sql, open(direct_meta, "w", encoding="utf-8") as f_meta:
        for tname, fields in direct:
            f_sql.write(f"CREATE TABLE {tname} (\n    " +
                        ",\n    ".join([f"{fld[0]} {fld[1]}" for fld in fields]) +
                        "\n);\n\n")
            f_meta.write(f"#TABLE {tname}\nFieldName|DataType|Start|End|Width\n")
            for fld in fields:
                f_meta.write(f"{fld[0]}|{fld[1]}|{fld[3]}|{fld[4]}|{fld[2]}\n")
            f_meta.write("\n")

    print(f"Expanded tables written to {expanded_sql} and {expanded_meta}")
    print(f"Direct tables written to {direct_sql} and {direct_meta}")
##-----------------------------------------------------------------------------