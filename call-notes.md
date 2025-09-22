Call Notes | Meeting #1
Call attendees: 
Chief Data Officer
Head of Data Management & Engineering
Data Engineering Lead

Call notes: 

Background:
There are a bunch of new data and security regulations in Singapore and Indonesia. Now that we are subjected to greater technical risk management that includes stringent cyber-security laws, we’re looking to operationalize security policies.

Problem Statements
Don’t have an inventory of sensitive data assets across their data pipeline
No easy way of classifying assets with PII identification and apply CIA ratings against information asset types (Sensitive client data vs non-sensitive)
Lack of end-to-end lineage means that the team has:
No traceability of the flow of PII through the entire data pipeline 
No visibility into the impact of schema changes which means that data engineers often have to manually review pipeline code when dashboards break downstream.
Understand business ownership back to data assets
Security abstraction layer that we can manage centrally (making sure that if our data asset classifications are done — we can manage access control) [Best we’ve seen is a DM tool that can help us query + leverage those]

Tech Stack
Data sources
Postgres – transactional database
S3 - landing zone
Snowflake - data warehouse
Looker - BI tool
Orchestration Tools
Airflow
Matillion
Single sign-on: Jump cloud (SAML 2.0)
Collaboration tools: Slack
Timeline of implementation
Can do POC asap

Data flow: 
We use Airflow DAGs to orchestrate the data flow from Postgres to S3 to the raw layer in Snowflake. Matillion used for transformations in Snowflake
Postgres → Moves to S3 → S3 to Snowflake → Looker
Within Snowflake - multiple zones are created by transformation queries pushed down by Matillion

Feedback on OvalEdge (Delta Arc Corp did a failed evaluation with them last month): 
Selected this tool because it covered all of their requirements. The rest of the tools did not.
Challenges:
Not all sources were supported with native connectors
Setup was difficult and lineage did not work as expected
Concerned about CS maturity to help them onboard


Users of Atlan Platform
15 people
DE + Management team: engineers 
Data analytics: BI developers + analysts
Data science: Data scientists
Business owners: look after domain data
Tech team: take care of source systems — also engineers 
Business users — 70 - 100 (projects + query)

Feedback
Query editor is good
Access control is good
UI is intuitive



Call Notes | Meeting #2
Call attendees: 
Chief Data Officer
Head of Data Management & Engineering
Data Engineering Lead

Agenda: Follow up deep-dive discussion on product and technical architecture

Call notes: 
I. Core Customer Ask
Need something with plug-and-play integrations: Postgres, S3, Snowflake, Looker. Need to understand where the data sets are and have end-to-end lineage across products. (Depends entirely on the integration piece)

II. Lineage and Business Glossary — These are a key feature requirements.
Delta Arctic: Can you run me through how Atlan’s lineage will work? 
Atlan: We’ll need to understand how your data pipeline is set up to understand how we’ll track lineage. 

III. Data Arctic’s Data Flow – Deeper Dive
Extract data from Postgres into S3 -- we just use the AWS library. This is happening on an incremental basis orchestrated by Airflow. 
Airflow orchestrates the loading of data from S3 into Snowflake
Data modeling in Snowflake occurs via Matillion pushing down SQL transformation queries that move data from raw -> cleaned -> presentation zones in Snowflake.
Looker is connected to the presentation tables in Snowflake.  


IV. Next StepsWould like to within Data Team (can
play roles of different types of users — e.g. business)
Need to understand native connections in data sources
We have different domains of data - would like to test end to end lineage (from source thru reporting layer)
Business glossary
Data catalog
Team members collaborate to build that up
Data classification / identifying PII 
Users: 13 people on the data team
The measure of success 1/ core functionality 2/ Ease of set up of business glossary 
