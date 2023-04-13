#!/usr/bin/python3

import concurrent.futures
import pandas as pd
import pdfplumber
import tabula
import magic
import re
import csv
from dateutil import parser
from datetime import datetime
import os
import logging


logging.basicConfig(filename='error.log', level=logging.ERROR)  # Specify log file and log level
# List to store invalid PDF files
invalid_files = []
unable_to_scan = []

# Some files are missing on the Skate AB page and do not propery give a 404 or other error page, but present a file to be downloaded.
def is_pdf(file):
    """
    Checks if a file is a valid PDF.

    Parameters:
        - file (str): The file path to check.

    Returns:
        - bool: True if the file is a valid PDF, False otherwise.
    """
    # Create a magic object to detect the MIME type of the file
    mime = magic.Magic(mime=True)
    # Get the MIME type of the file
    file_type = mime.from_file(file)
    # Compare the MIME type with 'application/pdf' to check if it's a PDF file
    if file_type != 'application/pdf':
        # If it's not a PDF, append the file to the list of invalid files
        invalid_files.append(file)
        return False
    return True



def load_mapping_from_csv(file_path):
    """Load mapping from a CSV file."""
    mapping = {}
    with open(file_path, mode='r') as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            key = row[reader.fieldnames[0]]
            value = row[reader.fieldnames[1]]
            mapping[key] = value
    return mapping

def normalize_name(name, mapping):
    """Normalize name based on mapping."""
    lower_name = name.strip().lower()  # Convert to lowercase
    mapping = {k.lower(): v for k, v in mapping.items()}  # Convert keys to lowercase
    normalized_name = mapping.get(lower_name, name)
    return normalized_name

def load_date_edge_cases(file_path):
    """Load date edge cases from CSV file to a dictionary."""
    date_edge_cases = {}
    with open(file_path, mode='r') as csv_file:
        reader = csv.DictReader(csv_file)
        date_edge_cases = {row['Edge Case']: row['Real Date'] for row in reader}
    return date_edge_cases

def extract_competition_name(lines):
    """Extract competition name from the first line of text."""
    return lines[0]

def extract_date(lines, date_edge_cases, months):
    """Extract start date from lines using date edge cases or regex pattern matching."""
    date_line = None
    category_name = None
    start_date = None
    for i in range(1, 4):
        for key in date_edge_cases:
            if key in lines[i]:
                start_date = date_edge_cases[key]
                category_name = lines[i + 1]
                break
        else:
            match = re.search(r"\b(" + "|".join(months) + r")\b", lines[i], re.IGNORECASE)
            if match:
                date_line = lines[i]
                category_name = lines[i + 1]
                break
            if date_line:
                break
    
    if not date_line:
        date_line = ""
    if not start_date:
        date_parts = date_line.split(" ")
        start_date = date_parts[0] + " " + date_parts[-1]
    return start_date, category_name

def competition_details(file):
    """Extract competition details from a PDF file."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
              "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    date_edge_cases = load_date_edge_cases('maps/date_edge_cases.csv')

    with pdfplumber.open(file) as pdf_document:
        first_page = pdf_document.pages[0]
        text_content = first_page.extract_text()
    lines = text_content.splitlines()
    
    competition_name = extract_competition_name(lines)
    start_date, category_name = extract_date(lines, date_edge_cases, months)


    # Normalize competition and category names using mappings
    # Load competition name mapping from CSV file
    comp_mapping = load_mapping_from_csv('maps/comp_map.csv')
    normalized_competition_name = normalize_name(competition_name, comp_mapping)
    competition_name = competition_name.strip()

    # Load category name mapping from CSV file
    category_mapping = load_mapping_from_csv('maps/category_mapping.csv')
    category_name = category_name.strip()
    normalized_category_name = normalize_name(category_name, category_mapping)

    return normalized_competition_name, start_date, normalized_category_name

def determine_category_type(category):
    competitive_categories = ["Senior", "Junior", "Novice", "Pre-Novice"]
    #Juvenile and Pre-Juvenile will trip things up, so we process them seperately. Pre-Juvenile U13 is not a Competitive event.
    for level in competitive_categories:
        if level in category:
            return "Competitive"
    if "Juvenile" in category:
        for criteria in ["U11", "U12", "U14", "U15", "Men", "Dance", "Pairs"]:
            if criteria in category:
                return "Competitive"    
    if "Adult" in category:
        return "Adult"
    if "Level" in category:
        return "Special Olympics"
    # Everything else is STARSkate
    return "STARSkate"

def determine_season(category_type, start_date):
    # Typically our competitive season ends with Sectionals in November. This is a bit weird, because the 2023 Competitive Season would run from
    # December 2023 to November 2024, ending with 2025 Sectionals - as Sectionals is qualifying for the 2025 Nationals.
    # The STARSkate season ends in March with AB STARSkate and Adult Championships

    date = parser.parse(start_date, fuzzy=True)

    # Determine start and end dates of season based on category
    if category_type == "Competitive":
        if date.month >= 12:
            start_date = f"{date.year}-12-01"
            end_date = f"{date.year + 1}-11-30"
        else:
            start_date = f"{date.year - 1}-12-01"
            end_date = f"{date.year}-11-30"
    else:
        if date.month >= 4:
            start_date = f"{date.year}-04-01"
            end_date = f"{date.year + 1}-03-31"
        else:
            start_date = f"{date.year - 1}-04-01"
            end_date = f"{date.year}-03-31"

    # Check if date is within the season
    if start_date <= start_date <= end_date:
        return end_date[:4]  # Extract the year from the end date
    else:
        return None

def is_Championship(competition_name):
    if "Championships" in competition_name:
        return True
    return False

# Create a column to define the type of program
def category_program_type(category_name, program_type_df):
    category_to_program_type = {
        'CS': 'Creative Skating Skill',
        'Triathlon': 'Triathalon',
        'Elements': 'Elements',
        'Special Olympics': 'Special Olympics',
        'SP': 'Short Program',
        'FS': 'Free Program',
        'Artistic': 'Artistic',
    }

    for key, value in category_to_program_type.items():
        if key in category_name:
            return program_type_df[program_type_df['Program_Type'] == value].index[0]
    return program_type_df[program_type_df['Program_Type'] == 'Combined'].index[0]

def add_to_dataframe(df, record):
    # Convert the record dictionary to a DataFrame
    name_to_check = record[next(iter(record))]
    if name_to_check in df.values:
        return df

    # Append the record to the DataFrame
    df_record = pd.DataFrame([record])
    df = pd.concat([df, df_record], ignore_index=True)
    return df

def parse_pdf(pdf_file):
    cat_results = pd.DataFrame()
    scan_area = [130, 13, 522, 775]
    tabula_scan = tabula.read_pdf(pdf_file, pages='all', stream=True, silent=True, area=scan_area)
    
    cat_results = pd.concat(tabula_scan, ignore_index=True)
    if cat_results.empty:
        print("empty df")
        unable_to_scan.append(pdf_file)
    print(pdf_file)

    # If this is a Category Results Summary for Pre-Novice or Novice Dance after the Pattern Dance we need to skip it, just return an empty dataframe
    if "FD" in cat_results.columns and cat_results['FD'].isnull().all():
        return pd.DataFrame()
        
    # Now clean up the dataframe.
    # First, if the column names are "Unnamed" we need to correct that
    if "Unnamed" in cat_results.columns[0]:
        new_header = cat_results.iloc[0] # grab the first row for the header
        cat_results = cat_results[1:] # take the data less the header row
        cat_results = cat_results.rename(columns=new_header) # set the header row as the df header
        cat_results.reset_index(drop=True, inplace=True)
        
    # Next we will remove any skaters that withdrew or were disqualified, they are not needed for this dataset. There is one that scans as MD. Kill that too
    cat_results = cat_results[cat_results['Rank'].isin(['WD', 'DQ', "MD"]) == False]
    
    # We could have rows at the bottom of the dataframe that are not skaters, there is also no rank,
    # so let's drop any row with NaN or no value as the rank
    cat_results =  cat_results.replace('', pd.NA)
    cat_results.dropna(subset=['Rank'], inplace=True)
    
    # Now there are many columns in this dataframe. Some have data, some are garbage. We will keep only the columns we want
    cat_results = cat_results.iloc[:, [cat_results.columns.get_loc('Rank'), cat_results.columns.get_loc('Competitor(s)'), cat_results.columns.get_loc('Club'),
                     cat_results.columns.get_loc('Section'), cat_results.columns.get_loc('Points')]]
    
    cat_results = cat_results.rename(columns={'Competitor(s)': 'Competitor'})
    
    # Set Rank as an integer
    cat_results['Rank'] = pd.to_numeric(cat_results['Rank']).astype(int)

    # Ensure Points is a number and has 2 decimal places
    cat_results['Points'] = pd.to_numeric(cat_results['Points'])
    cat_results['Points'] = cat_results['Points'].round(2).astype(float)
        
    # Reindex the Dataframe
    cat_results.reset_index(drop=True, inplace=True)
    
    return cat_results


def correct_club_names(cat_results, mapping_file):
    """
    Corrects the Club names in the category results DataFrame based on a mapping file.

    Args:
        cat_results (pd.DataFrame): Category results DataFrame.
        mapping_file (str): Path to the mapping file (CSV format).

    Returns:
        pd.DataFrame: Category results DataFrame with corrected Club names.
    """
    club_mapping = pd.read_csv(mapping_file)
    cat_results['Club'] = cat_results['Club'].map(club_mapping.set_index('Scraped')['Normalized']).fillna(cat_results['Club'])
    return cat_results

def correct_competition_names(competition_name, mapping_file):
    club_mapping = pd.read_csv(mapping_file)
    return competition_name

def add_to_df(results_df, df, column_name, new_column_name):
    # Get unique names from the results_df
    unique_names = results_df[column_name].dropna().unique()

    # Create a DataFrame to hold new names
    new_names_df = pd.DataFrame({new_column_name: unique_names})

    # Check if new names already exist in df
    existing_names = df[new_column_name].unique()
    new_names_df = new_names_df[~new_names_df[new_column_name].isin(existing_names)]

    # Update df with new names
    df = pd.concat([df, new_names_df], ignore_index=True)

    return df
    

def replace_names_with_ids(category_results_df, mapping_df, column_name, new_column_name):
    # Create a dictionary mapping names to their IDs in mapping_df
    name_mapping = mapping_df.reset_index().set_index(new_column_name).to_dict()['index']

    # Replace names in category_results_df with their IDs
    category_results_df[column_name] = category_results_df[column_name].map(name_mapping)

    return category_results_df

def add_competition_category_ids(category_results_df, competition_df, category_df, competition_name, category_name):
    # Find competition ID (index) from competition dataframe
    competition_id = competition_df[competition_df['Competition_Name'] == competition_name].index[0]

    # Find category ID (index) from category dataframe
    category_id = category_df[category_df['Category_Name'] == category_name].index[0]

    # Add competition ID and category ID to category_results_df
    category_results_df['Competition_ID'] = competition_id
    category_results_df['Category_ID'] = category_id

    return category_results_df

#Create a column that has a placement or placement range. This should aid in viz
def create_rank_bins(df):
    df['rank_bin'] = ''
    df.loc[df['Rank'] == 1, 'rank_bin'] = 'Gold'
    df.loc[df['Rank'] == 2, 'rank_bin'] = 'Silver'
    df.loc[df['Rank'] == 3, 'rank_bin'] = 'Bronze'
    df.loc[(df['Rank'] > 3) & (df['Rank'] <= 5), 'rank_bin'] = '4-5'
    df.loc[(df['Rank'] > 5) & (df['Rank'] <= 10), 'rank_bin'] = '6-10'
    df.loc[(df['Rank'] > 10) & (df['Rank'] <= 15), 'rank_bin'] = '11-15'
    df.loc[(df['Rank'] > 15) & (df['Rank'] <= 20), 'rank_bin'] = '16-20'
    df.loc[(df['Rank'] > 20) & (df['Rank'] <= 30), 'rank_bin'] = '21-30'
    df.loc[(df['Rank'] > 30) & (df['Rank'] <= 40), 'rank_bin'] = '31-40'
    df.loc[(df['Rank'] > 40) & (df['Rank'] <= 50), 'rank_bin'] = '41-50'
    df.loc[(df['Rank'] > 50), 'rank_bin'] = '50+'
    return df

def create_personal_best_df(results_df, competitor_df, category_df, program_type_df):
    
    df = results_df.merge(competitor_df, left_on='Competitor', right_index=True, how='inner') \
              .merge(category_df, left_on="Category_ID", right_index=True, how='inner') \
              .merge(program_type_df, left_on="Program_Type", right_index=True, how='inner')
    
    personal_best_df = df.groupby(["Competitor", "Program_Type"])["Points"].idxmax().reset_index()
    personal_best_df.rename(columns={'Points': 'Results_ID'}, inplace=True)
   
    return personal_best_df

def create_records(results_df, organization_df, category_df, org_name_field):
    df = results_df.merge(organization_df, left_on=org_name_field, right_index=True, how='inner') \
        .merge(category_df, left_on="Category_ID", right_index=True, how='inner')
    
    records_df = df.groupby([org_name_field, "Category_ID"])["Points"].idxmax().reset_index()
    records_df.rename(columns={'Points': 'Results_ID'}, inplace=True)
   
    return records_df
    
def create_recordfs_df(results_df, df1, df2, key1, key2, groupby_keys, rename_column, df3=None, key3=None):
    df = results_df.merge(df1, left_on=key1, right_index=True, how='inner') \
                   .merge(df2, left_on=key2, right_index=True, how='inner')
    
    if df3 is not None and key3 is not None:
        df = df.merge(df3, left_on=key3, right_index=True, how='inner')
    
    combined_df = df.groupby(groupby_keys)["Points"].idxmax().reset_index()
    combined_df.rename(columns={'Points': rename_column}, inplace=True)
   
    return combined_df

def process_header(pdf_file, competition_df, category_df, program_type_df):
    competition_name, start_date, category_name = competition_details(pdf_file)
    category_type = determine_category_type(category_name)
    season = determine_season(category_type, start_date)
    championship = is_Championship(competition_name)
    program_type = category_program_type(category_name, program_type_df)
    competition_df = add_to_dataframe(competition_df, {"Competition_Name": competition_name, "Start_Date": start_date, "Season": season,
                                                           "Championship": championship})
    category_df=add_to_dataframe(category_df, {"Category_Name": category_name, "Category_Type": category_type, "Program_Type": program_type})
    competition_id = competition_df[competition_df['Competition_Name'] == competition_name].index[0]
    category_id = category_df[category_df['Category_Name'] == category_name].index[0]

    return competition_df, category_df, competition_id, category_id, category_name
    
def process_results_table(pdf_file, clubs_df, competitor_df, competition_id, category_id, section_df):
    category_results_df = parse_pdf(pdf_file)
    category_results_df = correct_club_names(category_results_df, 'maps/club_mapping.csv')
    clubs_df = add_to_df(category_results_df, clubs_df, 'Club', 'Club_Name')
    category_results_df = replace_names_with_ids(category_results_df, clubs_df, 'Club', 'Club_Name')
    
    competitor_df = add_to_df(category_results_df, competitor_df, 'Competitor', 'Competitor_Name')
    category_results_df = replace_names_with_ids(category_results_df, competitor_df, 'Competitor', 'Competitor_Name')
    
    section_df = add_to_df(category_results_df, section_df, 'Section', 'Section')
    category_results_df = replace_names_with_ids(category_results_df, section_df, 'Section', 'Section')
    
    category_results_df['Competition_ID'] = competition_id
    category_results_df['Category_ID'] = category_id
    
    return category_results_df, clubs_df, competitor_df, section_df


def process_pdf(pdf_file, competition_df, category_df, clubs_df, competitor_df, program_type_df, section_df):
    competition_df, category_df, competition_id, category_id, category_name = process_header(pdf_file, competition_df, category_df, program_type_df)
    if "Pairs" in category_name or "Pair" in category_name or "Dance" in category_name or "Couples" in category_name:
        return pd.DataFrame(), competition_df, category_df, clubs_df, competitor_df, section_df
    category_results_df, clubs_df, competitor_df, section_df = process_results_table(pdf_file, clubs_df, competitor_df, competition_id, category_id, section_df)
    return category_results_df, competition_df, category_df, clubs_df, competitor_df, section_df


def main():
    pdf_dirs = "pdfs"
    pdf_files = [os.path.join(pdf_dirs, f) for f in os.listdir(pdf_dirs) if f.endswith('.pdf')]
    
    competition_df = pd.DataFrame()
    category_df = pd.DataFrame()
    clubs_df = pd.DataFrame(columns=["Club_Name"])
    section_df = pd.DataFrame(columns=["Section"])
    competitor_df = pd.DataFrame(columns=["Competitor_Name"])
    results_df = pd.DataFrame()
    program_type_df = pd.DataFrame({'Program_Type':
        ['Creative Skating Skill', 'Triathalon', 'Elements', 'Special Olympics', 'Short Program', 'Free Program', 'Artistic', 'Combined']})
    
    for pdf_file in pdf_files:
        try:
            if is_pdf(pdf_file):
                category_results_df, competition_df, category_df, clubs_df, competitor_df, section_df = process_pdf(pdf_file, competition_df, category_df, clubs_df, competitor_df, program_type_df, section_df)
                results_df = pd.concat([results_df, category_results_df], ignore_index=True)
        except Exception as e:
            logging.error(f"Error processing file: {pdf_file}. Error message: {e}")
    
    results_df = create_rank_bins(results_df)
    personal_best_df = create_personal_best_df(results_df, competitor_df, category_df, program_type_df)
    section_records_df = create_records(results_df, section_df, category_df, "Section")
    club_records_df = create_records(results_df, clubs_df, category_df, "Club")

    writer = pd.ExcelWriter("skate_ab_project.xlsx")
    
    section_df.to_excel(writer, sheet_name='Sections')
    clubs_df.to_excel(writer, sheet_name='Clubs')
    competitor_df.to_excel(writer, sheet_name='Competitors')
    competition_df.to_excel(writer, sheet_name='Competitions')
    category_df.to_excel(writer, sheet_name='Categories')
    program_type_df.to_excel(writer, sheet_name='Program Types')
    personal_best_df.to_excel(writer, sheet_name="Personal Bests")
    section_records_df.to_excel(writer, sheet_name="Section Records")
    club_records_df.to_excel(writer, sheet_name="Club Records")
    results_df.to_excel(writer, sheet_name='Results')
    
    writer.close()

    
main()

