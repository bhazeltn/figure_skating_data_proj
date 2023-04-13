# Figure Skating Competition Result Scraper
This is a Data Analysis project that will find all Category Results Summary pdf files on specified URLS, download the pdf files to a directory, then parse the pdf files for the data in them.

The data is then cleaned and normalized, organized into various tables, and exported to an Excel file. With the way the data is organized it could be put into a SQL database with minimal changes.

At this time the project is getting the files from Skate Canada: AB/NT/NU for competitions that are available on their website between January 2017 and March 2023. Only Singles categories are included, Dance, Pairs, and Couples categories do not add value to this dataset. Entries that had withdrawn from the event or were disqualified have been excluded from the data.

The visualization for this data has been created in Tableau Public and can be seen at https://public.tableau.com/app/profile/bradley.hazelton/viz/SkateABProject/Story1

Future plans for this project include:

 - Obtaining data from other Canadian Sections
 - Obtaining data from National events
 - Obtaining data from other Federations
 - Obtaining data from International events
 - Including Dance, Pairs, and Couples events
 - Including Syncronized Skating events