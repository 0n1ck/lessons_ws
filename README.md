# lessons_ws

Repository for web scraping of unob planned lessons

Use python3.10 as interpreter for creating .venv and running .py

## Lessons learned and stuff that I did.

1. I took 'subjectId', 'subjectName' and 'topic' from 'events' table
2. Took original strucure code from prof. Stefek which will be provided in this repository, and restructured it to 'plans'
3. I couldn't get to work triple query (see Stefek's code how his events scrape is connected with DBWriter)
4. I commented out DBwriter method from Analyzer class (so that just the scrape can work in debug mode)

## What is needed to be done?

1. Duplicite handling using ExternalIds
2. Maybe reform/update 'plans' table in systemdata.json
3. Add 'plan_lessons' table
4. Add 'aclessontypes' table
5. 2,3,4 Consult with prof. Stefek
6. GQL endpoint
7. do pipy and ipynb

## Make sure to and MUST READ

1. Add your own email address on 614 line
2. change 'plan_lessons' in main.py to 'plans' (I thought i made plan_lessons but after final consultation I realized I did 'plans' tables)
3. consult with prof. Stefek
