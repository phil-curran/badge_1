"""Build Badge 1 (Data Warehousing Workshop) lesson notebooks for Snowflake Workspaces.

Usage: python3 build_badge1_notebooks.py
Output: ../notebooks/badge1_dww/  (12 lesson notebooks, a setup notebook, a DORA notebook,
        the learner's Lesson 8 "Uncle Yers Root Depth Notebook", data/)

Course code is read verbatim from the Rise export. In lesson notebooks only role and
warehouse names are swapped for isolation variables:
    ACCOUNTADMIN -> {{ADMIN_ROLE}}     SYSADMIN -> {{SYSADMIN_ROLE}}     COMPUTE_WH -> {{WAREHOUSE}}
DORA code is never altered.
"""
import base64, html, json, os, re, shutil, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSE = os.path.join(ROOT, "badges", "badge-1-data-warehousing-workshop")
OUT = os.path.join(ROOT, "notebooks", "badge1_dww")

ADMIN_ROLE, SYSADMIN_ROLE, WAREHOUSE = "BADGE1_DWW_ADMIN", "BADGE1_DWW_ROLE", "BADGE1_DWW_WH"
DATA_FILES = ["veggie_details_a_to_k_comm.csv", "veggie_details_k_to_z_pipe.csv",
              "VEG_NAME_TO_SOIL_TYPE_PIPE.txt", "LU_SOIL_TYPE.tsv", "veg_plant_height.csv",
              "author_with_header.json", "json_book_author_nested.txt", "nutrition_tweets.json"]

# ---------------------------------------------------------------- course code
_raw = open(os.path.join(COURSE, "runtime-data.js")).read()
_course = json.loads(base64.b64decode(re.search(r'__jsonp\("runtime-data.js","(.*)"\)', _raw, re.S).group(1)))["course"]
CODE = {}
for _l in _course["lessons"]:
    _codes = [html.unescape(x.get("code") or "").replace("\r\n", "\n").strip("\n")
              for it in _l.get("items") or [] if it.get("type") == "multimedia" and it.get("variant") == "code"
              for x in it["items"]]
    if _codes:
        CODE[re.sub(r"<[^>]+>", "", _l["title"]).strip()] = _codes


def code(page, i=0):
    """Verbatim course code block i from the page whose title contains `page`."""
    hits = [k for k in CODE if page in k]
    assert len(hits) == 1, (page, hits)
    return CODE[hits[0]][i]


def isolate(sql):
    """Swap only role and warehouse names for the isolation variables."""
    sql = re.sub(r"\bACCOUNTADMIN\b", "{{ADMIN_ROLE}}", sql, flags=re.I)
    sql = re.sub(r"\bSYSADMIN\b", "{{SYSADMIN_ROLE}}", sql, flags=re.I)
    return re.sub(r"\bCOMPUTE_WH\b", "{{WAREHOUSE}}", sql, flags=re.I)


def dora_local(sql):
    """The DORA check with the external GRADER call removed, so it runs locally and sends nothing."""
    body = re.sub(r"select\s+GRADER\(step, \(actual = expected\), actual, expected, description\)\s+as graded_results\s+from",
                  "select step, actual, expected, (actual = expected) as passed, description from", sql, flags=re.I)
    if "GRADER" in body.upper().replace("GRADER FUNCTION", ""):  # multi-line GRADER( ... ) form (DWW08)
        body = re.sub(r"SELECT\s+GRADER\(.*?\)\s+AS\s+graded_results\s+FROM", "SELECT step, actual, expected, (actual = expected) AS passed, description FROM",
                      sql, flags=re.I | re.S)
    body = re.sub(r"(?im)^\s*use (role|database|schema)[^;]*;\s*$", "", body)
    return body.strip()


# ---------------------------------------------------------------- cell builders
def _id():
    return uuid.uuid4().hex[:8]


def md(text):
    return {"cell_type": "markdown", "id": _id(), "metadata": {}, "source": text.strip("\n")}


def sql(name, text):
    # Workspace notebooks expose a SQL cell's result to Python only under its `%%sql -r <name>` name
    # (otherwise as dataframe_N); in Snowsight this is the cell's "SQL as <name>" label.
    return {"cell_type": "code", "id": _id(), "execution_count": None, "outputs": [],
            "metadata": {"language": "sql", "name": name}, "source": f"%%sql -r {name}\n" + text.strip("\n")}


def split_statements(text):
    """Split a course code block into statements, text unchanged; comment lines stay with the statement after them."""
    parts, cur = [], []
    for line in text.split("\n"):
        cur.append(line)
        if line.rstrip().endswith(";") and not line.lstrip().startswith(("//", "--")):
            parts.append("\n".join(cur).strip("\n"))
            cur = []
    if "\n".join(cur).strip():
        parts.append("\n".join(cur).strip("\n"))
    return parts


def py(name, text):
    return {"cell_type": "code", "id": _id(), "execution_count": None, "outputs": [],
            "metadata": {"language": "python", "name": name}, "source": text.strip("\n")}


def course(text):
    """Quote course instructions (text or UI steps) in a markdown cell."""
    return md("> **Course:** " + text.strip().replace("\n", "\n> "))


def note(text):
    return md("> ⚠️ **Audit note:** " + text.strip().replace("\n", "\n> "))


def dora(step, what):
    return md(f"### 🤖 DORA check {step} goes here\n"
              f"The course has the learner run **{step}** ({what}) at this point.\n"
              f"It is in `{DORA_NB}.ipynb`, section **{step}**, as a local check plus the exact DORA code.")


def page(title):
    return md(f"## Page: {title}")


DOWNLOADS = "@UTIL_DB.PUBLIC.BADGE1_DOWNLOADS"
# Workspace layout (matches the badge_1 workspace as reorganized in Snowsight)
SETUP_NB, DORA_SETUP_NB, DORA_NB = "dora/account_setup", "dora/dora_setup", "dora/dora_tests"


def put(name, files, target):
    """SQL equivalent of the course's 'download the file, then upload it to the stage' steps.
    The course files sit on the BADGE1_DOWNLOADS stage, which stands in for the learner's Downloads folder."""
    file_list = ", ".join(f"'{f}'" for f in files)
    return sql(name, f"-- SQL equivalent of uploading the downloaded file(s) through the stage's + Files dialog\n"
                     f"use role {{{{ADMIN_ROLE}}}};\ncopy files into {target}\nfrom {DOWNLOADS}\nfiles = ({file_list});\n"
                     f"list {target};")


PREAMBLE_VARS = f"""# Isolation mapping (set once per notebook; SQL cells use these via {{{{...}}}})
ADMIN_ROLE    = "{ADMIN_ROLE}"   # stands in for the course's ACCOUNTADMIN
SYSADMIN_ROLE = "{SYSADMIN_ROLE}"    # stands in for the course's SYSADMIN
WAREHOUSE     = "{WAREHOUSE}"      # stands in for the course's COMPUTE_WH


def pdf(result):
    \"\"\"A SQL cell's result as pandas (runtime 2.6+ returns a Snowpark DataFrame).\"\"\"
    return result.to_pandas() if hasattr(result, "to_pandas") else result"""


def preamble(title, purpose):
    return [
        md(f"# Badge 1: Data Warehousing Workshop: {title}\n\n{purpose}\n\n"
           "**How to read this notebook**\n"
           "- Each `## Page:` heading is one page of the Rise lesson, in course order.\n"
           "- `> Course:` cells quote what the learner is told to do (text or screenshot steps).\n"
           "- Code cells run that task. Course code is verbatim except role/warehouse names, which are swapped for "
           f"`{ADMIN_ROLE}` (ACCOUNTADMIN), `{SYSADMIN_ROLE}` (SYSADMIN) and `{WAREHOUSE}` (COMPUTE_WH).\n"
           "- Cells marked **SQL equivalent** replace a UI-only step; **Derived solution** marks challenge-lab answers the course does not give.\n"
           f"- DORA checks are not run here; see `{DORA_NB}.ipynb`.\n"
           f"- Files the course has learners download are on the `{DOWNLOADS}` stage, which stands in for the learner's Downloads folder.\n\n"
           f"Prerequisite: run `{SETUP_NB}.ipynb` once."),
        py("isolation_vars", PREAMBLE_VARS),
        sql("session_context", "use role {{ADMIN_ROLE}};\nuse secondary roles none;\nuse warehouse {{WAREHOUSE}};\nselect current_role(), current_warehouse();"),
    ]


# ---------------------------------------------------------------- notebooks
NB = {}

NB[SETUP_NB] = [
    md(f"# Badge 1: Setup (run once, as ACCOUNTADMIN)\n\n"
       "Creates the isolated environment the lesson notebooks run in:\n\n"
       "| Course object | Isolated stand-in | Notes |\n|---|---|---|\n"
       f"| ACCOUNTADMIN role | `{ADMIN_ROLE}` | holds the account privileges the course uses as ACCOUNTADMIN |\n"
       f"| SYSADMIN role | `{SYSADMIN_ROLE}` | granted to `{ADMIN_ROLE}`, mirroring SYSADMIN under ACCOUNTADMIN |\n"
       f"| COMPUTE_WH | `{WAREHOUSE}` | X-Small, owned by `{ADMIN_ROLE}` (the Lesson 2 challenge transfers it) |\n"
       "| UTIL_DB | `UTIL_DB` | shared across badges; owned by SYSADMIN; the course assumes it exists (see audit note) |\n"
       f"| learner's Downloads folder | `{DOWNLOADS}` | holds the course data files the learner would download |\n\n"
       f"Hierarchy: `{SYSADMIN_ROLE}` → `{ADMIN_ROLE}` → SYSADMIN → ACCOUNTADMIN, so account admins still see everything.\n"
       "Object names (DEMO_DB, GARDEN_PLANTS, …) are the course's exact names."),
    py("isolation_vars", PREAMBLE_VARS),
    md("## Check for name collisions\nThe course's database names are account-wide. This lists any that already exist."),
    sql("existing_course_dbs", "use role accountadmin;\nshow databases;\nselect \"name\", \"owner\" from table(result_scan(last_query_id()))\nwhere \"name\" in ('DEMO_DB','GARDEN_PLANTS','UTIL_DB','LIBRARY_CARD_CATALOG','SOCIAL_MEDIA_FLOODGATES');"),
    md("## Roles and grants"),
    sql("create_roles", """use role accountadmin;
create role if not exists {{ADMIN_ROLE}} comment = 'Badge 1 stand-in for ACCOUNTADMIN';
create role if not exists {{SYSADMIN_ROLE}} comment = 'Badge 1 stand-in for SYSADMIN';
grant role {{SYSADMIN_ROLE}} to role {{ADMIN_ROLE}};
grant role {{ADMIN_ROLE}} to role sysadmin;
set badge_user = current_user();
grant role {{ADMIN_ROLE}} to user identifier($badge_user);
grant role {{SYSADMIN_ROLE}} to user identifier($badge_user);
-- trial ACCOUNTADMIN and SYSADMIN can both create databases
grant create database on account to role {{ADMIN_ROLE}};
grant create database on account to role {{SYSADMIN_ROLE}};"""),
    md("## Warehouse (stands in for COMPUTE_WH, owned by the ACCOUNTADMIN stand-in like in a trial)"),
    sql("create_warehouse", """use role accountadmin;
create warehouse if not exists {{WAREHOUSE}}
  warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true
  comment = 'Badge 1 stand-in for COMPUTE_WH';
grant ownership on warehouse {{WAREHOUSE}} to role {{ADMIN_ROLE}} copy current grants;"""),
    md("## UTIL_DB (shared across badges)"),
    note("The course never tells learners to create UTIL_DB, yet Lesson 2's checklist expects SYSADMIN to see it, "
         "and the DORA GRADER (Lesson 6) and MY_INTERNAL_STAGE (Lesson 9) live in it. It is probably provisioned by "
         "the course's special trial sign-up link; that could not be verified. Other badges use UTIL_DB too, so it is "
         "owned by SYSADMIN and each badge's roles get only the privileges they need."),
    sql("create_util_db", """use role accountadmin;
create database if not exists UTIL_DB comment = 'Shared utility database for badge course audits (DORA grader, course stages)';
grant ownership on database UTIL_DB to role sysadmin copy current grants;
grant ownership on schema UTIL_DB.PUBLIC to role sysadmin copy current grants;
grant usage on database UTIL_DB to role {{ADMIN_ROLE}};
grant usage on database UTIL_DB to role {{SYSADMIN_ROLE}};
grant usage, create stage, create file format, create workspace on schema UTIL_DB.PUBLIC to role {{ADMIN_ROLE}};
grant usage on schema UTIL_DB.PUBLIC to role {{SYSADMIN_ROLE}};"""),
    md("## Course data files (the learner's Downloads folder)\n"
       "The course has learners download 8 files and upload them through Snowsight. Here they sit on one stage, and each lesson "
       "copies them to the stage the course uses. The files are in `data/` beside these notebooks; upload them once with the "
       "Snowflake CLI:\n\n"
       "```\nsnow sql -q \"use role BADGE1_DWW_ADMIN; put 'file://<path>/data/*' @UTIL_DB.PUBLIC.BADGE1_DOWNLOADS auto_compress=false overwrite=true\"\n```\n\n"
       "or in Snowsight: Catalog → UTIL_DB → PUBLIC → Stages → BADGE1_DOWNLOADS → **+ Files**."),
    sql("create_downloads_stage", f"""use role {{{{ADMIN_ROLE}}}};
create stage if not exists {DOWNLOADS[1:]}
  comment = 'Badge 1: stands in for the learner''s local Downloads folder (course data files)'
  directory = (enable = true)
  encryption = (type = 'SNOWFLAKE_SSE');
grant read on stage {DOWNLOADS[1:]} to role {{{{SYSADMIN_ROLE}}}};
alter stage {DOWNLOADS[1:]} refresh;
list {DOWNLOADS};"""),
    py("downloads_check", f"""expected = {sorted(DATA_FILES)!r}
found = sorted(n.split('/')[-1] for n in pdf(create_downloads_stage)['name'])
print('Missing course files:', sorted(set(expected) - set(found)) or 'none')"""),
    md("## Keep each role's view isolated\n"
       "With secondary roles on, Snowsight shows the combined privileges of all your roles. Each lesson notebook runs "
       "`use secondary roles none`. To make Snowsight isolated too, uncomment the statement below."),
    sql("secondary_roles", "-- alter user identifier($badge_user) set default_secondary_roles = ();\nselect current_user(), current_secondary_roles();"),
    md("## Teardown (commented out)\nRemoves everything Badge 1 creates. Uncomment to reset."),
    sql("teardown", """-- use role accountadmin;
-- drop database if exists DEMO_DB;
-- drop database if exists GARDEN_PLANTS;
-- drop database if exists LIBRARY_CARD_CATALOG;
-- drop database if exists SOCIAL_MEDIA_FLOODGATES;
-- UTIL_DB is shared with other badges; drop only Badge 1's objects in it
-- drop stage if exists UTIL_DB.PUBLIC.MY_INTERNAL_STAGE;
-- drop stage if exists UTIL_DB.PUBLIC.BADGE1_DOWNLOADS;
-- drop resource monitor if exists daily_3_credit_limit;
-- drop warehouse if exists {{WAREHOUSE}};
-- drop role if exists {{SYSADMIN_ROLE}};
-- drop role if exists {{ADMIN_ROLE}};
select 'teardown is commented out' as status;"""),
]

NB["lesson_01_getting_started"] = preamble("Lesson 1: Getting Started", "Lesson 1 is videos, quizzes and trial sign-up; there are no lab tasks. This notebook checks the account against the course's trial requirements.") + [
    page("🎭 Meet Tsai! / 🎭 Why a Trial Account?"),
    md("Videos and knowledge checks only; nothing to execute."),
    page("🧭 Set Up Your Trial Account"),
    course("Sign up for a Snowflake Trial Account on AWS … If you choose not to use the link above, be sure to choose ENTERPRISE, AWS, US West (Oregon)."),
    sql("account_details", "select current_organization_name() as org, current_account_name() as account, current_account() as locator,\n       current_region() as region, current_user() as user_name, current_version() as version;"),
    py("trial_requirement_check", """region = pdf(account_details)["REGION"][0]
print("Region:", region)
print("Matches course requirement (AWS US West Oregon):", region.upper().endswith("AWS_US_WEST_2"))
print("Edition must be ENTERPRISE; check Admin > Accounts in Snowsight (not exposed to SQL without ORGADMIN).")"""),
    note("The course says the sign-up link gives 120 days instead of the standard 30, and that the badge may not be "
         "issued outside AWS US West (Oregon). This audit account is not a trial, so trial-only behavior (credits, "
         "pre-provisioned objects) can differ."),
]

NB["lesson_02_identity_and_access"] = preamble("Lesson 2: Identity & Access", "Databases, ownership, roles, and the warehouse ownership challenge.") + [
    page("🤔 UI Changed? Of course it has!"),
    md("Reading and a knowledge check only."),
    page("🥋 Create a Database"),
    course("UI steps (screenshot DWW_006): Catalog → Database Explorer → **+ Database** → Name **DEMO_DB** → **Create**. Dialog shows *Owner: ACCOUNTADMIN*."),
    sql("create_demo_db", "-- SQL equivalent of the UI steps, run as the ACCOUNTADMIN stand-in\nuse role {{ADMIN_ROLE}};\ncreate database DEMO_DB;"),
    page("🥋 Explore Your New Database"),
    course("Explore the database you created (DWW_011). How many schemas are included? What are their names? What is inside each schema?"),
    sql("explore_demo_db", "show schemas in database DEMO_DB;"),
    sql("demo_db_owner", "show databases like 'DEMO_DB';"),
    page("🥋 Transfer Ownership of Your New Database"),
    course("UI steps (DWW_013, DWW_014): DEMO_DB → **…** → **Transfer Ownership** → Transfer to **SYSADMIN** → **Transfer**."),
    sql("transfer_demo_db", "-- SQL equivalent of Transfer Ownership\ngrant ownership on database DEMO_DB to role {{SYSADMIN_ROLE}};\nshow databases like 'DEMO_DB';"),
    course("🥋 Switch Your System Role Back to SYSADMIN (DWW_008)."),
    sql("switch_to_sysadmin", "use role {{SYSADMIN_ROLE}};\nselect current_role();"),
    page("🎭 Identity vs. Access"),
    md("Knowledge checks only."),
    page("🥋 Changing Your Role Setting"),
    course("UI steps (DWW_016): Governance & security → Users & roles → **Roles** → **Graph**; click each role name and read what each role does."),
    sql("role_graph", "-- SQL equivalent of the Roles graph for the isolated roles\nuse role {{ADMIN_ROLE}};\nshow grants to role {{ADMIN_ROLE}};"),
    sql("role_graph_sysadmin", "show grants of role {{SYSADMIN_ROLE}};"),
    page("📓 RBAC Review / 🎭 DAC Model & Default Role"),
    course("Because of the combination of RBAC and DAC in Snowflake, when we create something, the ROLE we were using at the time we created it is the role that OWNS it."),
    sql("dac_demo", "-- DEMO_DB now belongs to SYSADMIN, but its PUBLIC schema still belongs to the creating role\nshow schemas in database DEMO_DB;"),
    page("📓 Roles and Warehouse Visibility"),
    course("Three warehouses were created for you (DWW_022): COMPUTE_WH (owned by ACCOUNTADMIN), a learning/sandbox warehouse, and SYSTEM$STREAMLIT_NOTEBOOK_WH."),
    note("The page contains two copies of this text that disagree: one says the second warehouse is **SANDBOX_WH**, the other **SNOWFLAKE_LEARNING_WH**. Screenshot DWW_022 shows SANDBOX_WH."),
    sql("warehouses_as_sysadmin", "use role {{SYSADMIN_ROLE}};\nshow warehouses;"),
    sql("warehouses_as_admin", "use role {{ADMIN_ROLE}};\nshow warehouses;"),
    course("🎯 CHALLENGE LAB: Make the Warehouse Available to SYSADMIN. Transfer the COMPUTE_WH warehouse to SYSADMIN. (UI, DWW_023: Compute → Warehouses → COMPUTE_WH → … → Transfer Ownership → SYSADMIN → Transfer.)"),
    sql("transfer_warehouse", "-- Derived solution (SQL equivalent of the UI transfer)\ngrant ownership on warehouse {{WAREHOUSE}} to role {{SYSADMIN_ROLE}} copy current grants;\nuse role {{SYSADMIN_ROLE}};\nshow warehouses;"),
    page("🏁 Summary & Next Steps"),
    course("Are you ready for Lesson 3? Can see the COMPUTE_WH warehouse while in the SYSADMIN role · Can see your DEMO_DB database when SYSADMIN · Can see your UTIL_DB database when SYSADMIN."),
    sql("ready_check", "use role {{SYSADMIN_ROLE}};\nshow databases;"),
    py("ready_check_eval", """names = set(pdf(ready_check)["name"])
for db in ["DEMO_DB", "UTIL_DB"]:
    print(f"{db} visible to SYSADMIN stand-in:", db in names)"""),
    note(f"This checklist expects **UTIL_DB**, which the course has not told the learner to create (see `{SETUP_NB}`)."),
]

NB["lesson_03_data_containers"] = preamble("Lesson 3: Data Containers", "GARDEN_PLANTS and its schemas, files and context, and SHOW commands.") + [
    page("🪴 Uncle Yer's Plant Shop"),
    md("Video and knowledge checks only."),
    page("🎯 Set Up Uncle Yer's Database & Schemas"),
    course("Set your role to SYSADMIN. Create a Database and name it GARDEN_PLANTS. Drop the PUBLIC schema that was automatically created. "
           "Create three new schemas in your GARDEN_PLANTS database. Name them VEGGIES, FRUITS and FLOWERS."),
    sql("garden_plants_setup", """-- Derived solution (the course gives instructions, not code)
use role {{SYSADMIN_ROLE}};
create database GARDEN_PLANTS;
drop schema GARDEN_PLANTS.PUBLIC;
create schema GARDEN_PLANTS.VEGGIES;
create schema GARDEN_PLANTS.FRUITS;
create schema GARDEN_PLANTS.FLOWERS;"""),
    sql("garden_plants_schemas", "show schemas in database GARDEN_PLANTS;"),
    page("🥋 Create an Worksheet & Run Some Code"),
    course("Workspaces: Projects → Workspaces → + Add new → SQL File (DWW_024–026). Every .sql file has 4 context drop menus: role, warehouse, database, schema (DWW_028)."),
    note("Page title says “Create an Worksheet” (grammar) and the body mixes “SQL Worksheets” and “SQL files” for the same step."),
    sql("set_context", "-- SQL equivalent of setting the four context menus\nuse role {{SYSADMIN_ROLE}};\nuse warehouse {{WAREHOUSE}};\nuse database GARDEN_PLANTS;\nuse schema VEGGIES;\nselect current_role(), current_warehouse(), current_database(), current_schema();"),
    page("📓 Knowing What Will Run"),
    md("Reading and knowledge checks only."),
    page("🥋 Running SHOW Commands"),
    course("Run the SHOW DATABASES command (DWW_039)."),
    sql("show_databases", "show databases;"),
    course("Run the SHOW SCHEMAS command (DWW_040)."),
    sql("show_schemas", "show schemas;"),
    course("Change the Database Context and Run the SHOW SCHEMAS Command Again (DWW_042)."),
    sql("show_schemas_demo_db", "use database DEMO_DB;\nshow schemas;"),
    course("There is another SHOW SCHEMAS command: SHOW SCHEMAS IN ACCOUNT. What happens if you add “IN ACCOUNT”? How does the context menu affect the results?"),
    sql("show_schemas_in_account", "show schemas in account;"),
    page("🎯 Lesson 3 Challenge Lab"),
    course("Make sure SYSADMIN can see all the databases and schemas that have been created. If that role cannot see everything ACCOUNTADMIN can see, FIX IT. Also, make sure there is no PUBLIC schema in the GARDEN_PLANTS database."),
    sql("dbs_as_admin", "use role {{ADMIN_ROLE}};\nshow databases;"),
    sql("dbs_as_sysadmin", "use role {{SYSADMIN_ROLE}};\nshow databases;"),
    sql("garden_schemas_check", "show schemas in database GARDEN_PLANTS;"),
    py("challenge_check", """course_dbs = {"DEMO_DB", "GARDEN_PLANTS", "UTIL_DB"}
missing = course_dbs & set(pdf(dbs_as_admin)["name"]) - set(pdf(dbs_as_sysadmin)["name"])
print("Course databases ADMIN sees but SYSADMIN does not:", missing or "none")
print("PUBLIC schema still in GARDEN_PLANTS:", "PUBLIC" in set(pdf(garden_schemas_check)["name"]))"""),
]

NB["lesson_04_tables_data_types_loading"] = preamble("Lesson 4: Tables, Data Types, and Loading Data", "ROOT_DEPTH table, INSERT, SELECT * with LIMIT, and the challenge rows.") + [
    page("🎭 Uncle Yer Goes from Spreadsheets to SQL"),
    md("Video and knowledge checks only."),
    page("🥋 Create the ROOT_DEPTH Table"),
    course("Create Your ROOT_DEPTH Table. Screenshot DWW_048 shows context **SYSADMIN · COMPUTE_WH · GARDEN_PLANTS · VEGGIES**."),
    sql("context_root_depth", "use role {{SYSADMIN_ROLE}};\nuse warehouse {{WAREHOUSE}};\nuse database GARDEN_PLANTS;\nuse schema VEGGIES;"),
    sql("create_root_depth", code("Create the ROOT_DEPTH Table")),
    course("Find the Table You Just Created in the Workspace Database Explorer (DWW_049). If you can't find it: refresh the picker, try the search box, run a SHOW command."),
    sql("find_root_depth", "show tables in schema GARDEN_PLANTS.VEGGIES;"),
    course("View the Definition of Your Table (DWW_052). Notice that the SQL shown is different than the SQL we ran. What changes were made?"),
    sql("root_depth_ddl", "select get_ddl('table', 'GARDEN_PLANTS.VEGGIES.ROOT_DEPTH') as table_definition;"),
    page("🥋 Insert a Row of Data into Your New Table"),
    course("Use the Data Preview Option: find the table in the Database Explorer, open the ellipses menu, click Preview Table. Note that your table has zero rows."),
    sql("preview_before", "-- SQL equivalent of Data Preview\nselect * from GARDEN_PLANTS.VEGGIES.ROOT_DEPTH limit 100;"),
    sql("insert_shallow", code("Insert a Row of Data")),
    sql("preview_after", "-- Preview Your ROOT_DEPTH Table Again\nselect * from GARDEN_PLANTS.VEGGIES.ROOT_DEPTH limit 100;"),
    page("📓 Select Stars and Limits"),
    sql("select_star_limit", code("Select Stars and Limits")),
    page("🎯 Lesson 4 Challenge Lab"),
    course("Edit the Insert Statement (twice) and run it (twice) to add two additional rows in your ROOT_DEPTH table. Target rows (DWW_056): 2 · M · Medium · cm · 45 · 60 and 3 · D · Deep · cm · 60 · 90."),
    sql("insert_medium", "-- Derived solution: the course insert statement, edited per DWW_056\ninsert into root_depth \nvalues\n(\n    2,\n    'M',\n    'Medium',\n    'cm',\n    45,\n    60\n);"),
    sql("insert_deep", "insert into root_depth \nvalues\n(\n    3,\n    'D',\n    'Deep',\n    'cm',\n    60,\n    90\n);"),
    course("Run your SELECT * to view all three rows. Compare your results with the screenshot (DWW_057)."),
    sql("root_depth_all", "SELECT * FROM  ROOT_DEPTH;"),
    md("The course's “New to SQL?” block is labelled *THESE ARE JUST EXAMPLES! YOU SHOULD NOT RUN THIS CODE*, so it is shown here but not run:\n\n```sql\n" + code("Lesson 4 Challenge Lab") + "\n```"),
    note("That example block has syntax errors as written: the multi-row INSERT is missing the `values` keyword, and the UPDATE has no WHERE clause (it would update every row)."),
    course("🏁 Ready for Lesson 5? Do you have 5 Databases? Are all 5 visible by ACCOUNTADMIN and by SYSADMIN? Does GARDEN_PLANTS have 4 schemas? Does VEGGIES have a single table ROOT_DEPTH with 3 rows?"),
    sql("ready_dbs", "use role {{SYSADMIN_ROLE}};\nshow databases;"),
    sql("ready_schemas", "show schemas in database GARDEN_PLANTS;"),
    sql("ready_rows", "select count(*) as root_depth_rows from GARDEN_PLANTS.VEGGIES.ROOT_DEPTH;"),
    py("ready_eval", """print("Databases visible to SYSADMIN stand-in:", sorted(pdf(ready_dbs)["name"]))
print("GARDEN_PLANTS schema count:", len(pdf(ready_schemas)), "(course expects 4)")
print("ROOT_DEPTH rows:", int(pdf(ready_rows)["ROOT_DEPTH_ROWS"][0]), "(course expects 3)")"""),
    note("The checklist expects 5 databases, but the course's own screenshot DWW_043 shows 4 (DEMO_DB, GARDEN_PLANTS, SNOWFLAKE, SNOWFLAKE_LEARNING_DB), and UTIL_DB was never created by the learner. The count depends on trial-provisioned databases."),
]

NB["lesson_05_worksheets_and_warehouses"] = preamble("Lesson 5: Worksheets & Warehouses", "Context menus, warehouse sizing, and the resource monitor.") + [
    page("🎭 Tsai Tells the Team About Worksheets & Warehouses"),
    course("ROLE and WAREHOUSE drop menu values are REQUIRED. DATABASE and SCHEMA values are SUGGESTED STARTING POINTS."),
    sql("required_context", "select current_role() as role, current_warehouse() as warehouse, current_database() as database, current_schema() as schema;"),
    page("🎭 What is a Warehouse in Snowflake?"),
    sql("warehouse_size", "show warehouses like '{{WAREHOUSE}}';"),
    page("📓 Just Because You Can..."),
    course("Snowflake recommends always starting with eXtra-Small warehouses … keep your warehouse set to XS except in cases where we ask you to use size S."),
    page("🥋 Set Up A Resource Monitor"),
    course("UI steps (DWW_059): Admin → Cost Management → Resource Monitors → **+ Resource Monitor**. Name **daily_3_credit_limit**, Credit Quota **3**, Monitor Type **Account**; Customize schedule: Start **Immediately**, End **Never**, Resets **Daily**; Actions: **95%** suspend immediately and notify, **85%** suspend and notify, **75%** notify → **Create Resource Monitor**."),
    note("Creating resource monitors requires ACCOUNTADMIN, so this cell uses the real ACCOUNTADMIN. The course applies the monitor to the whole **Account**; in this shared audit account that would suspend every warehouse after 3 credits a day, so the monitor is applied to the Badge 1 warehouse instead. The account-level statement is shown, commented out."),
    sql("create_resource_monitor", """-- SQL equivalent of the UI steps
use role accountadmin;
create resource monitor if not exists daily_3_credit_limit with
  credit_quota = 3
  frequency = daily
  start_timestamp = immediately
  triggers on 95 percent do suspend_immediate
           on 85 percent do suspend
           on 75 percent do notify;
-- Course: Monitor Type = Account
-- alter account set resource_monitor = daily_3_credit_limit;
-- Isolated equivalent: apply to the Badge 1 warehouse only
alter warehouse {{WAREHOUSE}} set resource_monitor = daily_3_credit_limit;
show resource monitors like 'daily_3_credit_limit';"""),
    page("📓 Getting Notified"),
    course("Click your user name → Settings → Notifications to receive email alerts about Resource Monitors (UI only; nothing to run)."),
    page("🏁 Summary & Next Steps"),
    md("Knowledge check only."),
]

NB["lesson_06_meet_dora"] = preamble("Lesson 6: Meet DORA!", f"DORA setup is in `{DORA_SETUP_NB}.ipynb`; checks DWW01–05 are in `{DORA_NB}.ipynb`. This notebook runs the non-DORA metadata queries.") + [
    page("🎭 Meet DORA!"),
    md("### 🤖 DORA setup goes here\nThe course has the learner (as ACCOUNTADMIN) create the `dora_api_integration` API integration, the "
       "`util_db.public.grader` external function, and run the `DORA_IS_WORKING` test. " f"All three are in `{DORA_SETUP_NB}.ipynb`."),
    page("🥋 Preparing for Code Checks"),
    course("Using Code to Check Your Work: you were asked to set up 3 schemas in a GARDEN_PLANTS database and delete a schema. Run some code to see if you did those tasks."),
    sql("schemata_all", isolate(code("Preparing for Code Checks", 0))),
    md("📓 *How Can I Fix Things?* The course shows these fixes for mistakes; they are not run here:\n\n```sql\nALTER SCHEMA GARDEN_PLANTS.WEGGIES RENAME TO GARDEN_PLANTS.VEGGIES;\nALTER SCHEMA DEMO_DB.VEGGIES RENAME TO GARDEN_PLANTS.VEGGIES;\n```"),
    sql("schemata_by_name", isolate(code("Preparing for Code Checks", 1))),
    sql("schemata_count", isolate(code("Preparing for Code Checks", 2))),
    note("The counting query (“Counting the Number of Correctly Named Schemas”) has no WHERE clause, so it counts all schemas (5 including INFORMATION_SCHEMA), not the 3 correctly named ones the text describes."),
    page("🔍 What is Metadata?"),
    md("Knowledge checks only."),
    dora("DWW01", "Created 3 Garden Plant schemas"),
    dora("DWW02", "Deleted PUBLIC schema"),
    dora("DWW03", "ROOT_DEPTH Table Exists"),
    dora("DWW04", "UTIL_DB Schemas"),
    dora("DWW05", "ROOT_DEPTH row count"),
    page("👂 DORA is Listening!"),
    course("Visit https://ysa.snowflakeuniversity.com to edit your name/email, format your badge display name, link your learning account to your trial account, and view your DORA checks (needs UNI_ID and UUID). Outside Snowflake; nothing to run."),
]

NB["lesson_07_load_data_wizard"] = preamble("Lesson 7: The Load Data Wizard", "VEGETABLE_DETAILS, loading two files, and the duplicate-Spinach cleanup.") + [
    page("🎭 Insert Statements Get Old, Fast"),
    course("Create a Vegetable Details Table. Screenshot DWW_076 shows context **GARDEN_PLANTS.VEGGIES**; the role is not shown."),
    note("Screenshots disagree on the owner: DWW_088 (this lesson) shows VEGETABLE_DETAILS owned by SYSADMIN, DWW_099 (Lesson 8) shows ACCOUNTADMIN. This notebook follows SYSADMIN, the course's stated convention."),
    sql("create_vegetable_details", "use role {{SYSADMIN_ROLE}};\nuse schema GARDEN_PLANTS.VEGGIES;\n" + code("Insert Statements Get Old")),
    page("🥋 Loading Table Rows from a File (A to K)"),
    course("Download this file (veggie_details_a_to_k_comma_opt_enclosed.csv) and upload it into your Veggie Details table using the Load Data wizard (DWW_078–084): "
           "table → Load Data → choose file → File format **Delimited Files (CSV or TSV)** → View options → Header **First line contains header** → map *Plant Name* → PLANT_NAME and *Rooting Depth* → ROOT_DEPTH_CODE → **Load**."),
    note("The export's copy of the file is named `veggie_details_a_to_k_comm.csv` (Rise truncated the name); the contents are the same file."),
    sql("load_a_to_k", f"""-- SQL equivalent of the Load Data wizard: the wizard reads the learner's downloaded file directly
copy into GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS
from {DOWNLOADS}
files = ('veggie_details_a_to_k_comm.csv')
file_format = (type = 'CSV' field_delimiter = ',' skip_header = 1 field_optionally_enclosed_by = '"');"""),
    page("🥋 Loading Table Rows from a File (K to Z)"),
    course("🎯 Challenge Lab: Load the second file (veggie_details_k_to_z_pipe.csv) into the same table using the same method. The columns are NOT separated by commas this time."),
    sql("load_k_to_z", f"""-- Derived solution: same wizard settings, Field delimiter changed to |
copy into GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS
from {DOWNLOADS}
files = ('veggie_details_k_to_z_pipe.csv')
file_format = (type = 'CSV' field_delimiter = '|' skip_header = 1 field_optionally_enclosed_by = '"');"""),
    course("Check your table by running a select statement. You should see 42 rows. If you reverse the sort order, you should see Zucchini at the top."),
    sql("check_42_rows", "select * from GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS order by plant_name desc;"),
    py("check_42_eval", "rows = pdf(check_42_rows)\nprint('Rows:', len(rows), '(course expects 42)'); print('Top row:', rows['PLANT_NAME'][0])"),
    md("The course's reset statement, if a file was loaded twice (not run):\n\n```sql\nTRUNCATE TABLE GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS;\n```"),
    dora("DWW06", "VEGETABLE_DETAILS Table"),
    page("🎯 Viewing Our Table Data"),
    course("View your data · Notice a plant name that appears twice · Find a way to get rid of it · View your data again (DWW_090–094)."),
    sql("view_veg", "select * from GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS;"),
    sql("find_spinach", "-- Derived from DWW_091\nselect * from GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS where plant_name = 'Spinach';"),
    sql("isolate_spinach_d", "-- Derived from DWW_092\nselect * from GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS where plant_name = 'Spinach' and root_depth_code = 'D';"),
    sql("delete_spinach_d", "-- From DWW_093\nuse schema GARDEN_PLANTS.VEGGIES;\ndelete from vegetable_details\nwhere plant_name = 'Spinach'\nand root_depth_code = 'D';"),
    sql("no_duplicates", "-- Derived from DWW_094\nselect plant_name, count(*) as n from GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS group by plant_name having count(*) > 1;"),
    dora("DWW07", "VEG_DETAILS row count, expects 41"),
]

LEARNER_NB = "Uncle Yers Root Depth Notebook"   # DWW_103
APP_TITLE = "Uncle Yers Root Depth Entry Form"    # DWW_126
APP_NAME = f'garden_plants.fruits."{APP_TITLE}"'
APP_FILE = f'snow://streamlit/GARDEN_PLANTS.FRUITS."{APP_TITLE}"/versions/live/streamlit_app.py'
NOTEBOOK_TITLE_CELL = "# Add Rows to Flower Detail Table\n\nEdit the \"set\" cells to update the variables, then click \"Run All\" in the top left-corner."
APP_CODE = '''# Import python packages
import streamlit as st
from snowflake.snowpark.context import get_active_session

# Write directly to the app
st.title(":apple: Uncle Yer's Fruit Details :apple:")
st.write(
    """Enter fruit name and root depth code below.
    """
)

# Get the current credentials
session = get_active_session()


fn = st.text_input('Fruit Name:')
rdc = st.selectbox('Root Depth:', ('S','M','D'))

if st.button('Submit'):
    # st.write('Fruit Name entered is ' + fn)
    # st.write('Root Depth Code chosen is ' + rdc)
    sql_insert = 'insert into garden_plants.fruits.fruit_details select \\''+fn+'\\',\\''+rdc+'\\''
    # st.write(sql_insert)
    result = session.sql(sql_insert)
    st.write(result)
'''

NB["lesson_08_notebooks_and_forms"] = preamble("Lesson 8: Notebooks & Forms", "FLOWER_DETAILS via a notebook with session variables, FRUIT_DETAILS via a Streamlit-in-Snowflake form.") + [
    page("📓 Other Ways for Interacting with Data!"),
    course("Copy the CREATE TABLE code from the VEGETABLE_DETAILS table (DWW_099: Catalog → Database Explorer → GARDEN_PLANTS → VEGGIES → VEGETABLE_DETAILS → Table definition → copy), paste it, change the name to FLOWER_DETAILS, set the context to GARDEN_PLANTS.FLOWERS, and run it (DWW_100). The screenshot's role is ACCOUNTADMIN."),
    sql("copy_veg_ddl", "-- SQL equivalent of copying the Table definition\nselect get_ddl('table', 'GARDEN_PLANTS.VEGGIES.VEGETABLE_DETAILS') as table_definition;"),
    sql("create_flower_details", "-- Pasted and edited per DWW_100\nuse role {{ADMIN_ROLE}};\nuse schema GARDEN_PLANTS.FLOWERS;\ncreate or replace TABLE FLOWER_DETAILS (\n    PLANT_NAME VARCHAR(25),\n    ROOT_DEPTH_CODE VARCHAR(1)\n);"),
    note("DWW_100 creates FLOWER_DETAILS as ACCOUNTADMIN, contrary to the course's rule that SYSADMIN should own everything."),
    page("🥋 Create a Snowflake Notebook"),
    course("UI steps (DWW_103): Projects → Workspaces → + Add new → **Notebook** named **Uncle Yers Root Depth Notebook** → Connect → Create new service **NOTEBOOK_SERVICE** → Create and connect. Add a Markdown cell."),
    md(f"The learner's notebook is the separate file **`{LEARNER_NB}.ipynb`** in this workspace. It is shipped in the course's final state: "
       "the six cells named and ordered as in DWW_114, with the contents from DWW_116, DWW_117, DWW_120 and DWW_121. "
       "Do the steps below **in that notebook**, as the course describes. This lesson notebook has no copies of its cells.\n\n"
       f"Isolation: in that notebook's header, choose role **`{ADMIN_ROLE}`** (for the course's ACCOUNTADMIN) and warehouse **`{WAREHOUSE}`** (for COMPUTE_WH). "
       "Its cells contain only the course's code."),
    note("DORA check DWW08 looks in SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY for an object matching '%Uncle Yer%'. Whether a Workspace notebook's name appears there could not be verified."),
    page("🥋 Add Cells to the Notebook"),
    course("Add a SQL cell, name it **insert_row**, paste the insert statement, and run the cell (DWW_111):\n\n```sql\n" + code("Add Cells to the Notebook") + "\n```\n\n"
           "🎯 Create another SQL cell, name it **check_the_table**, write a SELECT * statement on the flower_details table, and run the cell."),
    md("**In the learner's notebook:** the shipped `insert_row` cell already holds its final version (`select $fn, $rdc;`). "
       "To do this step as written, put the Petunia statement above into `insert_row`, run it, then run `check_the_table`."),
    page("🥋 Use Variables in the Notebook"),
    course("🎯 Create 3 more SQL cells named set_flower_name, set_root_depth_code and check_my_variables, and rearrange them into the order shown (DWW_114). Fill in the new SQL cells and run them:\n\n```sql\n"
           + code("Use Variables in the Notebook") + "\n```\n\n"
           "Replace the flower name & root depth code in `insert_row` with the variables (DWW_117), run it, then run the last cell to check your insert (DWW_118)."),
    md("**In the learner's notebook:** run `set_root_depth_code`, `set_flower_name`, `check_my_variables`, `insert_row` and `check_the_table` (or **Run All**). This inserts Lilac / S."),
    page("🥋 Put Finishing Touches on Your Notebook"),
    course("Edit your Markdown cell (DWW_120). 🎯 Use your notebook to create 3 additional rows in the Flower Detail table: A Sunflower should have deep roots. Lavender can have shallow roots. "
           "A Tulip has a bulb, not roots, but we'll say they need medium root depth. Run the last cell to check your inserted rows (DWW_121 shows Petunia M, Lilac S, Sunflower D, Lavender S, Tulip M)."),
    md("**In the learner's notebook:** `Title_Cell` already has the DWW_120 text. For each flower, edit the two set cells and click **Run All**:\n\n"
       "| Run | `set_root_depth_code` | `set_flower_name` |\n|---|---|---|\n"
       "| 1 | `set rdc = 'D';` | `set fn = 'Sunflower';` |\n| 2 | `set rdc = 'S';` | `set fn = 'Lavender';` |\n| 3 | `set rdc = 'M';` | `set fn = 'Tulip';` |\n\n"
       "The D/S/M codes are derived from the course text. Then run the check below."),
    sql("check_flower_rows", "-- Confirms the learner's notebook runs (DWW_121); not a course cell\nselect * from garden_plants.flowers.flower_details;"),
    dora("DWW08", "Notebook success!"),
    page("🥋 Create a SiS Form"),
    course("🎯 Create a Fruit Details Table: model it after the other 2 details tables (DWW_124 shows FRUIT_DETAILS in GARDEN_PLANTS.FRUITS)."),
    sql("create_fruit_details", "-- Derived solution: same columns as VEGETABLE_DETAILS and FLOWER_DETAILS\nuse role {{ADMIN_ROLE}};\ncreate or replace table garden_plants.fruits.fruit_details (\n    PLANT_NAME VARCHAR(25),\n    ROOT_DEPTH_CODE VARCHAR(1)\n);"),
    course("UI steps (DWW_126): Projects → Streamlit → **+ Streamlit App** → **Create on warehouse (legacy)** → App title **Uncle Yers Root Depth Entry Form**, location **GARDEN_PLANTS / FRUITS**, warehouse **COMPUTE_WH** → Create. "
           "Then (DWW_128–142) delete the sample code from line 18 down, edit the title and instruction line, add the input fields, capture them in `fn` and `rdc`, add a Submit button, build `sql_insert` with escaped quotes, comment out the write lines, and run the SQL."),
    md("The course's code snippets, in order:\n\n```python\n" + code("Enable the SiS Form") + "\n```\n```python\n" + code("Capturing Form Entries") + "\n```\n```python\n" + code("Prepare an Insert Statement") + "\n```"),
    note("The app builds SQL by concatenating user input (`'insert … select \\''+fn+'\\',\\''+rdc+'\\''`), a SQL-injection pattern. A fruit name containing an apostrophe (e.g. *Dragon's Eye*) breaks the insert. Consider teaching parameter binding."),
    sql("create_streamlit_app", f"""-- SQL equivalent of the Create Streamlit App dialog (DWW_126): Create on warehouse (legacy),
-- App title, App location GARDEN_PLANTS / FRUITS, App warehouse. Like the dialog, this starts the app from Snowflake's sample code.
use role {{{{ADMIN_ROLE}}}};
create streamlit {APP_NAME}
  runtime_name = 'SYSTEM$WAREHOUSE_RUNTIME'
  query_warehouse = {{{{WAREHOUSE}}}}
  title = '{APP_TITLE}';
alter streamlit {APP_NAME} add live version from last;"""),
    note(f"Snowsight assigns the app's object identifier itself; the course shows only the title. Here the identifier is the title, `{APP_NAME}`."),
    py("edit_streamlit_app_code", f'''# SQL equivalent of the code edits in the Streamlit editor (DWW_128 to DWW_142): the course's final app code,
# with the DWW_139 escape fix, is written into the app's live version.
import io
from snowflake.snowpark.context import get_active_session
session = get_active_session()
APP_CODE = {APP_CODE!r}
session.file.put_stream(io.BytesIO(APP_CODE.encode()),
                        {APP_FILE!r},
                        auto_compress=False, overwrite=True)
print(APP_CODE)'''),
    page("🥋 Writing Our Entries to the Database"),
    course("🎯 Check your FRUIT_DETAILS table to see if you added a row. Once you have confirmed that your app works, add two more rows (for a total of 3). You can use any fruit names with any root depth settings."),
    py("simulate_submits", '''# A notebook cannot click the app's Submit button. This runs the exact statement the app builds,
# once per entry. Apricot/S matches DWW_142; the other two are chosen here.
from snowflake.snowpark.context import get_active_session
session = get_active_session()
for fn, rdc in [("Apricot", "S"), ("Blueberry", "S"), ("Cherry", "M")]:
    sql_insert = 'insert into garden_plants.fruits.fruit_details select \\''+fn+'\\',\\''+rdc+'\\''
    print(sql_insert, "->", session.sql(sql_insert).collect())'''),
    sql("check_fruits", "select * from garden_plants.fruits.fruit_details;"),
    md("**Manual step:** DORA check DWW09 looks in QUERY_HISTORY for `execute streamlit \"GARDEN_PLANTS\".\"FRUITS\".%`, which only appears when the app is opened in Snowsight. Open *Uncle Yers Root Depth Entry Form* under Projects → Streamlit once before running DWW09."),
    dora("DWW09", "SiS App Works"),
]

# The learner's own notebook (DWW_103), in the course's final state: cell names and order from DWW_114,
# contents from DWW_116 (set cells), DWW_117 (insert_row), DWW_120 (Title_Cell) and DWW_121 (check_the_table).
_title_cell = md(NOTEBOOK_TITLE_CELL)
_title_cell["metadata"] = {"name": "Title_Cell"}
_set_code = code("Use Variables in the Notebook").split("\n")
NB[LEARNER_NB] = [
    _title_cell,
    sql("set_root_depth_code", _set_code[0]),
    sql("set_flower_name", _set_code[1]),
    sql("check_my_variables", _set_code[2]),
    sql("insert_row", "insert into garden_plants.flowers.flower_details\nselect $fn, $rdc;"),
    sql("check_the_table", "select *\nfrom garden_plants.flowers.flower_details;"),
]

NB["lesson_09_staging_data"] = preamble("Lesson 9: Staging Data", "MY_INTERNAL_STAGE, file formats, COPY INTO, and the two challenge loads.") + [
    page("🥋 Create a Snowflake Stage Object"),
    course("UI steps (DWW_145–147): UTIL_DB / PUBLIC → **Create** → **Stage** → **Snowflake Managed** → Stage Name **my_internal_stage**, schema **UTIL_DB.PUBLIC**, Comment **a place to hold files before loading them**, Directory table **on**, Encryption **Server-side** → **Create**. The dialog says *Creating as ACCOUNTADMIN*."),
    sql("create_stage", "-- SQL equivalent of the Create Stage dialog\nuse role {{ADMIN_ROLE}};\ncreate stage util_db.public.my_internal_stage\n  comment = 'a place to hold files before loading them'\n  directory = (enable = true)\n  encryption = (type = 'SNOWFLAKE_SSE');"),
    dora("DWW10", "Internal stage created"),
    page("🥋 Load a File into Your Stage"),
    course("Download a file (VEG_NAME_TO_SOIL_TYPE_PIPE.txt) & upload it to your stage (DWW_149, DWW_150: stage → + Files → browse → Upload)."),
    put("put_soil_type_file", ["VEG_NAME_TO_SOIL_TYPE_PIPE.txt"], "@util_db.public.my_internal_stage"),
    md("The course's COPY INTO template (illustrative, not run):\n\n```sql\n" + code("Load a File into Your Stage") + "\n```"),
    page("🥋 Use the COPY INTO Statement to Load Data"),
    course("Create a Table for Soil Types. Make sure you create it in the GARDEN_PLANTS database, in the VEGGIES schema. (Role not specified.)"),
    note("The stage was created as ACCOUNTADMIN, so SYSADMIN cannot read it. Where the course does not name a role, these cells use the ACCOUNTADMIN stand-in so the COPY INTO succeeds as it would for a trial user on the default role."),
    sql("create_soil_type_table", "use role {{ADMIN_ROLE}};\nuse schema GARDEN_PLANTS.VEGGIES;\n" + code("Use the COPY INTO Statement", 0)),
    sql("create_pipe_ff", code("Use the COPY INTO Statement", 1)),
    sql("copy_soil_type", code("Use the COPY INTO Statement", 2)),
    dora("DWW11", "Veg Det Soil Type Count, expects 42"),
    page("🥋 Query a File Before You Load It"),
    course("🎯 Download and upload this file (LU_SOIL_TYPE.tsv) into your stage."),
    put("put_lu_soil_type", ["LU_SOIL_TYPE.tsv"], "@util_db.public.my_internal_stage"),
    sql("create_comma_ff", code("Query a File Before You Load It", 0)),
    course("Explore the Effect of File Formats On Data Interpretation."),
] + [sql(f"explore_ff_{i+1}", stmt.strip()) for i, stmt in enumerate(code("Query a File Before You Load It", 1).split(";")) if stmt.strip()] + [
    page("🎯 Challenge Lab: Create a File Format, Use it in a COPY INTO"),
    course("Create a file format that will help you load files with these properties. Name the file format: **L9_CHALLENGE_FF**. Make sure the data looks like the screenshot (DWW_154) when you use your new File Format in the query. "
           "Tip: if columns were separated by a tab, you would put FIELD_DELIMITER = '\\t'."),
    sql("create_l9_challenge_ff", "-- Derived solution: tab-delimited, one header row; TRIM_SPACE handles the padded values in the file\ncreate or replace file format garden_plants.veggies.L9_CHALLENGE_FF\n    type = 'CSV'\n    field_delimiter = '\\t'\n    skip_header = 1\n    trim_space = true;"),
    sql("test_l9_challenge_ff", "select $1, $2, $3\nfrom @util_db.public.my_internal_stage/LU_SOIL_TYPE.tsv\n(file_format => garden_plants.veggies.L9_CHALLENGE_FF);"),
    course("Create a Soil Type Look Up Table in GARDEN_PLANTS.VEGGIES. Also, make sure it is owned by the SYSADMIN role."),
    sql("create_lu_soil_type", "use role {{SYSADMIN_ROLE}};\nuse schema GARDEN_PLANTS.VEGGIES;\n" + code("Challenge Lab: Create a File Format", 0)),
    course("🎯 Create a COPY INTO command to load LU_SOIL_TYPE.tsv from your stage to the LU_SOIL_TYPE table. DO NOT use 'SKIP_FILE' or 'CONTINUE' for ON_ERROR. Run a SELECT * to see if it loaded nicely."),
    sql("copy_lu_soil_type", "-- Derived solution (run as the ACCOUNTADMIN stand-in, which can read the stage)\nuse role {{ADMIN_ROLE}};\ncopy into garden_plants.veggies.lu_soil_type\nfrom @util_db.public.my_internal_stage\nfiles = ('LU_SOIL_TYPE.tsv')\nfile_format = (format_name = garden_plants.veggies.L9_CHALLENGE_FF);"),
    sql("check_lu_soil_type", "select * from garden_plants.veggies.lu_soil_type;"),
    page("🎯 Challenge Lab: Create a Table, Use It in a COPY INTO!"),
    course("Create a table called VEGETABLE_DETAILS_PLANT_HEIGHT in the VEGGIES schema, using the file's header row for column names and good data types. Upload veg_plant_height.csv to your stage. Choose an existing file format. Use a COPY INTO command to load it."),
    sql("create_plant_height", "-- Derived solution: header is plant_name, UOM, Low_End_of_Range, High_End_of_Range\nuse role {{SYSADMIN_ROLE}};\ncreate or replace table garden_plants.veggies.VEGETABLE_DETAILS_PLANT_HEIGHT (\n    plant_name varchar(25),\n    UOM varchar(1),\n    Low_End_of_Range number(2,0),\n    High_End_of_Range number(2,0)\n);"),
    put("put_plant_height", ["veg_plant_height.csv"], "@util_db.public.my_internal_stage"),
    sql("copy_plant_height", "-- Derived solution: the existing comma-separated file format fits this file\nuse role {{ADMIN_ROLE}};\ncopy into garden_plants.veggies.VEGETABLE_DETAILS_PLANT_HEIGHT\nfrom @util_db.public.my_internal_stage\nfiles = ('veg_plant_height.csv')\nfile_format = (format_name = garden_plants.veggies.COMMASEP_DBLQUOT_ONEHEADROW);"),
    sql("check_plant_height", "select count(*) as rows_loaded from garden_plants.veggies.VEGETABLE_DETAILS_PLANT_HEIGHT;"),
    dora("DWW12", "Veg Detail Plant Height Count, expects 41"),
    dora("DWW13", "Soil Type Look Up Table, expects 8"),
    dora("DWW14", "Challenge File Format Created"),
    page("👂 Check In With DORA"),
    course("Use the YSA app (https://ysa.snowflakeuniversity.com) to see which tests DORA has received and whether they passed and were valid. Outside Snowflake; nothing to run."),
]

NB["lesson_10_data_storage_structures"] = preamble("Lesson 10: Data Storage Structures", "LIBRARY_CARD_CATALOG: BOOK, AUTHOR, a sequence, and the BOOK_TO_AUTHOR bridge table.") + [
    page("🎭 Data Storage: A Short History"),
    md("Video and knowledge checks only."),
    page("🥋 Create the Library Card Catalog DB"),
    sql("create_library_db", isolate(code("Create the Library Card Catalog DB"))),
    page("🎭 Data Storage: Entities and Relationships / From ERDs to Tables"),
    md("Videos and knowledge checks only."),
    page("🥋 Create and Fill the Books Table"),
    sql("create_fill_book", isolate(code("Create and Fill the Books Table"))),
    page("🥋 Create the Author Table"),
    sql("create_author", isolate("use role sysadmin;\nuse database library_card_catalog;\n" + code("Create the Author Table"))),
    note("The Create the Author Table code has no `use` statements; it relies on the context set on the previous page. The `use` lines above make that explicit."),
    page("🥋 Create a Sequence"),
    course("UI steps (DWW_156, DWW_156a): Catalog → Database Explorer → LIBRARY_CARD_CATALOG → PUBLIC → **Create** → **Sequence**; the dialog generates the SQL below. NOTE: If you do not include the word ORDER, your values will skip by 100 each time."),
    sql("create_sequence", "-- SQL from the Create Sequence dialog (DWW_156a)\nuse role {{SYSADMIN_ROLE}};\nuse schema library_card_catalog.public;\ncreate sequence SEQ_AUTHOR_UID\n    start = 1,\n    increment = 1,\n    ORDER,\n    comment = 'Use this to fill in AUTHOR_UID';"),
    course("View the Sequence Object: notice that the Next Value column says “1” (DWW_159)."),
    sql("show_sequence_1", "show sequences;"),
    sql("query_sequence", isolate(code("Create a Sequence"))),
    course("Run the query a few more times and see how the next_value changes. When the show sequences result shows next_value = 4, stop."),
    sql("query_sequence_2", "select seq_author_uid.nextval;"),
    sql("query_sequence_3", "select seq_author_uid.nextval;"),
    sql("show_sequence_4", "show sequences;"),
    course("Double It Up! You can use nextval more than once per query (DWW_162)."),
    sql("double_it_up", "SELECT SEQ_AUTHOR_UID.nextval, SEQ_AUTHOR_UID.nextval;\n"),
    sql("show_sequence_after", "show sequences;"),
    page("🥋 Reset the Sequence & Add Rows to the Author Table"),
    # Split at the course block's own statement boundary: the notebook SQL runner does not treat `//` as a
    # comment, so the apostrophe in "we'll" merges both statements (fails with "statement count 2 ... 1").
    sql("reset_sequence", isolate(code("Reset the Sequence")).split("\n\n//Add the remaining")[0]),
    sql("add_authors", "//Add the remaining" + isolate(code("Reset the Sequence")).split("\n\n//Add the remaining")[1]),
    note("The course's code block for this step is split into two cells unchanged: Workspace notebooks do not treat "
         "`//` as a comment, so the apostrophe in the comment *then we'll add…* makes the block fail when run as one cell. "
         "The same block runs fine in a Snowsight worksheet."),
    page("🎭 Data Storage: Mapping the Many-to-Many"),
    md("Video and knowledge checks only."),
    page("🥋 Create the Book_To_AUTHOR Table"),
    sql("create_book_to_author", isolate(code("Create the Book_To_AUTHOR Table"))),
    dora("DWW15", "3NF DB was Created, expects 6"),
]

NB["lesson_11_intro_semi_structured"] = preamble("Lesson 11: Intro to Semi-Structured Data", "AUTHOR_INGEST_JSON, a JSON file format, and querying VARIANT data.") + [
    page("🎭 Semi-Structured Data Formats"),
    md("Video and knowledge checks only."),
    page("🎯 Create JSON Table & File Format, and Load the File"),
    course("🎯 Download a JSON File (author_with_header.json). Notice the square bracket that surrounds the author records; it could cause all the data to end up in a single row."),
    sql("create_author_ingest_json", isolate(code("Create JSON Table & File Format", 0))),
    course("🎯 Create a File Format to Load the JSON Data: replace each <?> with TRUE or FALSE. The default for each setting is FALSE. To load the file data into separate rows, one of the values will need to be set to TRUE."),
    md("Course template:\n\n```sql\n" + code("Create JSON Table & File Format", 1) + "\n```"),
    sql("create_json_ff", "-- Derived solution: STRIP_OUTER_ARRAY = TRUE splits the bracketed array into rows\ncreate file format library_card_catalog.public.json_file_format\ntype = 'JSON' \ncompression = 'AUTO' \nenable_octal = FALSE\nallow_duplicate = FALSE \nstrip_outer_array = TRUE\nstrip_null_values = FALSE \nignore_utf8_errors = FALSE; "),
    course("🎯 Load the data into the new table using the file format you created. Test the file format first by querying the file (DWW_165). Stage: @util_db.public.my_internal_stage."),
    put("put_author_json", ["author_with_header.json"], "@util_db.public.my_internal_stage"),
    note("The JSON table is owned by SYSADMIN but the stage by ACCOUNTADMIN; the test query and COPY INTO run as the ACCOUNTADMIN stand-in."),
    sql("test_json_ff", "use role {{ADMIN_ROLE}};\nselect $1\nfrom @util_db.public.my_internal_stage/author_with_header.json\n(file_format => library_card_catalog.public.json_file_format);"),
    sql("copy_author_json", "-- Derived solution\ncopy into library_card_catalog.public.author_ingest_json\nfrom @util_db.public.my_internal_stage\nfiles = ('author_with_header.json')\nfile_format = (format_name = library_card_catalog.public.json_file_format);"),
    course("🎯 View the JSON Rows (DWW_166)."),
    sql("view_author_json", "select * from library_card_catalog.public.author_ingest_json;"),
    page("🥋 Query the JSON Table"),
    sql("query_author_json", "use database library_card_catalog;\nuse schema public;\n" + code("Query the JSON Table")),
    dora("DWW16", "Check number of rows, expects 6"),
]

NB["lesson_12_nested_semi_structured"] = preamble("Lesson 12: Nested Semi-Structured Data", "NESTED_INGEST_JSON, FLATTEN, and the SOCIAL_MEDIA_FLOODGATES tweet data.") + [
    page("🎭 Nested JSON"),
    md("Video and knowledge checks only."),
    page("🥋 Load and Query Nested Author & Book JSON Data"),
    sql("create_nested_ingest", "use role {{SYSADMIN_ROLE}};\n" + code("Load and Query Nested Author", 0)),
    course("🎯 Download the data file (json_book_author_nested.txt) and load it into NESTED_INGEST_JSON. You can use the file format you created for the non-nested JSON data."),
    put("put_nested_json", ["json_book_author_nested.txt"], "@util_db.public.my_internal_stage"),
    sql("copy_nested_json", "-- Derived solution\nuse role {{ADMIN_ROLE}};\ncopy into library_card_catalog.public.nested_ingest_json\nfrom @util_db.public.my_internal_stage\nfiles = ('json_book_author_nested.txt')\nfile_format = (format_name = library_card_catalog.public.json_file_format);"),
    sql("query_nested", "use schema library_card_catalog.public;\n" + code("Load and Query Nested Author", 1)),
    sql("flatten_nested", code("Load and Query Nested Author", 2)),
    page("🎭 PATH Notation for Nested Entities"),
    md("Video and knowledge checks only."),
    dora("DWW17", "Check number of rows, expects 5"),
    page("🎭 Some Old Twitter Tweets / 🥋 Explore the Data with an Online Parser"),
    course("Download nutrition_tweets.json and open it in https://jsoneditoronline.org/ (DWW_167–170). Outside Snowflake; nothing to run."),
    note("The tweet data is from an old Twitter/X API export. The file starts with a UTF-8 byte-order mark, which Snowflake's JSON loader skips by default."),
    page("🥋 Load and Query Nested TWEET JSON Data"),
    course("🎯 Create a database named SOCIAL_MEDIA_FLOODGATES. Create a table called TWEET_INGEST in its PUBLIC schema with one column named RAW_STATUS. Create a FILE FORMAT of type JSON. Write a COPY INTO that loads the tweet data; stage the file wherever you decide. You should end up with 9 rows."),
    sql("tweets_infrastructure", "-- Derived solution\nuse role {{SYSADMIN_ROLE}};\ncreate database SOCIAL_MEDIA_FLOODGATES;\ncreate table social_media_floodgates.public.tweet_ingest (raw_status variant);\ncreate file format social_media_floodgates.public.json_file_format\n    type = 'JSON'\n    strip_outer_array = TRUE;"),
    put("put_tweets", ["nutrition_tweets.json"], "@util_db.public.my_internal_stage"),
    sql("copy_tweets", "-- Derived solution\nuse role {{ADMIN_ROLE}};\ncopy into social_media_floodgates.public.tweet_ingest\nfrom @util_db.public.my_internal_stage\nfiles = ('nutrition_tweets.json')\nfile_format = (format_name = social_media_floodgates.public.json_file_format);"),
    sql("query_tweets_1", "use schema social_media_floodgates.public;\n" + split_statements(code("Load and Query Nested TWEET JSON Data"))[0]),
    *[sql(f"query_tweets_{i}", s) for i, s in enumerate(split_statements(code("Load and Query Nested TWEET JSON Data"))[1:], 2)],
    note("The course's code block is split into one cell per statement, text unchanged. Workspace notebooks do not treat `//` as a comment, "
         "so the apostrophes in *doesn't* and *tweet's* merge statements and the block fails when run as one cell."),
    page("🥋 Flatten & Isolate Entities"),
    sql("flatten_urls", code("Flatten & Isolate Entities", 0)),
    sql("flatten_hashtags", code("Flatten & Isolate Entities", 1)),
    dora("DWW18", "Check number of rows, expects 9"),
    page("🥋 Normalize the Hashtags"),
    sql("create_urls_normalized", code("Normalize the Hashtags")),
    course("🎯 Create a view called HASHTAGS_NORMALIZED. The results of SELECT * on your view should look like DWW_172 (USER_NAME, TWEET_ID, HASHTAG_USED; 14 rows)."),
    sql("create_hashtags_normalized", "-- Derived solution, modeled on URLS_NORMALIZED and the hashtag flatten query\ncreate or replace view social_media_floodgates.public.hashtags_normalized as\n(select raw_status:user:name::text as user_name\n,raw_status:id as tweet_id\n,value:text::varchar as hashtag_used\nfrom tweet_ingest\n,lateral flatten\n(input => raw_status:entities:hashtags)\n);"),
    sql("check_hashtags", "select * from social_media_floodgates.public.hashtags_normalized;"),
    py("check_hashtags_eval", "print('Rows:', len(pdf(check_hashtags)), '(DWW_172 shows 14)')"),
    dora("DWW19", "HASHTAGS_NORMALIZED view exists"),
    page("🎉 Badge Time!"),
    course("Check in with DORA in the YSA app: all DORA tests DWW01–DWW19 should be PASSING and VALID. Outside Snowflake; nothing to run."),
]

# ---------------------------------------------------------------- DORA notebook
DORA_PAGES = [("DWW01", 6), ("DWW02", 6), ("DWW03", 6), ("DWW04", 6), ("DWW05", 6), ("DWW06", 7), ("DWW07", 7),
              ("DWW08", 8), ("DWW09", 8), ("DWW10", 9), ("DWW11", 9), ("DWW12", 9), ("DWW13", 9), ("DWW14", 9),
              ("DWW15", 10), ("DWW16", 11), ("DWW17", 12), ("DWW18", 12), ("DWW19", 12)]
dora_intro = ("# Badge 1: DORA checks\n\n"
       "Every DORA step from the course, in order. Each check has two cells:\n\n"
       "1. **Local check**: the course's check query with the external `GRADER` call removed. It runs entirely in this account and sends nothing.\n"
       "2. **DORA (exact course code)**: verbatim and unedited, as the course requires (DORA audits a hash of the code).\n\n"
       "⚠️ **Running a DORA cell, or the Setup cells, sends data outside this account.** The GRADER is an external function that calls "
       "Snowflake Education's grading service (`https://awy6hshxy4.execute-api.us-west-2.amazonaws.com/dev/edu_dora`) with the step "
       "result plus `current_account`, `current_account_name`, `current_statement` and a timestamp. Run only the local checks unless you intend to submit.\n\n"
       "DORA code uses the real `ACCOUNTADMIN`, as the course specifies. Each local check names the lesson notebook it follows.")
# Split as in the badge_1 workspace: DORA setup (Lesson 6) and the DORA checks are separate notebooks
NB[DORA_SETUP_NB] = [
    md(dora_intro),
    md("## Setup (course Lesson 6, 🎭 Meet DORA!)\nThe course: *You don't have to understand what it means to “create an API Integration,” you just need to run the code below (using the ACCOUNTADMIN ROLE!).*"),
    sql("dora_api_integration", code("Meet DORA!", 0)),
    sql("dora_grader_function", code("Meet DORA!", 1)),
    md("### Is the GRADER Function working?"),
    sql("dora_is_working", code("Meet DORA!", 2)),
]
dora_cells = [md(dora_intro)]
for step, lesson in DORA_PAGES:
    c = code(f"DORA {step}")
    dora_cells += [
        md(f"## {step} (after `lesson_{lesson:02d}`)"),
        sql(f"{step.lower()}_local", "use role accountadmin;\n-- Local check: same query without the GRADER call\n" + dora_local(c)),
        sql(f"{step.lower()}_dora", c),
    ]
NB[DORA_NB] = dora_cells

# ---------------------------------------------------------------- write
META = {"jupytext": {"main_language": "sql"},
        "kernelspec": {"display_name": "Streamlit Notebook", "name": "streamlit"}}

# Replace only generated files: OUT is also a Git working copy (.git must survive a rebuild)
for sub in ("data", "dora"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
for sub in ("", "dora"):
    for old in [f for f in os.listdir(os.path.join(OUT, sub)) if f.endswith(".ipynb")]:
        os.remove(os.path.join(OUT, sub, old))
for f in DATA_FILES:
    shutil.copy(os.path.join(COURSE, "assets", f), os.path.join(OUT, "data", f))
for name, cells in NB.items():
    names = [c["metadata"].get("name") for c in cells if c["cell_type"] == "code"]
    assert len(names) == len(set(names)), (name, [n for n in names if names.count(n) > 1])
    json.dump({"cells": cells, "metadata": META, "nbformat": 4, "nbformat_minor": 5},
              open(os.path.join(OUT, f"{name}.ipynb"), "w"), indent=1)
    print(f"{name:42s} cells={len(cells):3d}  code={len(names):3d}")
print("data files:", len(DATA_FILES), "->", os.path.join(OUT, "data"))
