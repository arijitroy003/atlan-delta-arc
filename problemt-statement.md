🧩 Atlan CSA Challenge — Candidate Brief

Hi there 👋 and congratulations!

You've made it to the challenge round of the Customer Solutions Architect (CSA) interview process at Atlan — and that’s no small feat. This means we already see great potential in you, and now we want to give you a real-world, hands-on chance to show us how you think, build, and solve.
This challenge is designed to be as real as it gets — just like the work you'd be doing at Atlan. It’s not a trick test. It’s a sandbox where you show us how you'd step into a customer scenario, solve a real metadata problem, and deliver real value.

🎯 The Purpose
For You:
Get up close with Atlan’s product, market, and customer culture


Decide if this is the team, mission, and environment where you want to do your best work


For Us:
Understand how you think and solve problems


Evaluate your ability to consult, build, and communicate effectively with customers


Assess how you fit into our technical culture and team DNA



🔍 The Scenario: Delta Arc Corp
You’ve just joined Atlan as a CSA and are assigned to onboard a new customer: Delta Arc Corp, a fintech startup based in Singapore. They had a quick pre-sale cycle with no full POC, and now you’re tasked with:
Understanding their pipeline


Helping them integrate S3 into Atlan’s lineage graph


Guiding them toward an effective metadata strategy


Their stack looks like this:
 PostgreSQL → S3 → Snowflake → Looker
Atlan supports Postgres, Snowflake, and Looker natively. But S3 is not natively connected, so you’ll need to build a custom ingestion and lineage solution for that.

🚧 Challenge Goals
You’ll demonstrate your ability to:
Understand a customer’s technical and strategic challenges


Design a solution that balances feasibility, scalability, and impact


Implement a working integration using Atlan’s SDK


Communicate the solution in a clear, customer-ready format



✅ Required Deliverables
Please submit the following:
1. Solution Design Document (PDF or Doc)
Your architecture proposal for integrating S3 into the lineage flow.
Must include:
Executive summary of the challenge


Architecture diagram (current vs. target state)


How the solution works (components, flow, tooling)


Metadata & lineage approach


Implementation phases (timeline or plan)


Potential business outcomes and KPIs



2. Python Script Using pyatlan SDK
A script that:
Registers the given S3 bucket and objects as Atlan assets


Establishes lineage from PostgreSQL → S3 → Snowflake
NOTE: When creating the asset for this bucket in Atlan, your script will need to have logic to uniquely name the ARN of the bucket as this is required to be unique across all buckets in the Atlan instance. Because the same bucket is being reused for multiple candidates, our suggestion is to suffix with initials or similar in your code when translating from the actual ARN to the ARN used in Atlan.

3. Slide Deck (for Customer Mock)
Imagine you're presenting to the Head of Data and Data Engineering Lead at Delta Arc Corp.
Your deck should include:
Problem understanding


Proposed solution and architecture


Timeline/phased rollout


AI or automation opportunities (optional but encouraged)


Measurable business value



🧠 Bonus (Optional)
Choose any (or none):
Deploy the script on a cloud-native service (e.g., AWS Lambda, GCP Functions)


Demonstrate how AI can enhance metadata quality, lineage inference, or governance (describe or prototype)



🧪 Technical Environment
Atlan Instance: https://tech-challenge.atlan.com
 (You'll receive an invite from support@atlan.com)


S3 Bucket (read-only): arn:aws:s3:::atlan-tech-challenge
 View in browser: Link


Preloaded Connections:
Postgres Assets: postgres-<your initials>


Snowflake Assets: snowflake-<your initials>


Resources to Help You:
Product Docs


Developer Portal


University Training


Atlan Values




🧭 What “Great” Looks Like
Here’s how we evaluate submissions:
Category
What We’re Looking For
Discovery & Customer Framing
Are you solving the right problem for the customer personas?
Architecture & Design
Is the solution scalable, maintainable, and clearly communicated?
Code & Implementation
Is your script working, clean, and well-structured?
Product Fluency
Do you use Atlan terminology and core concepts correctly?
Presentation & Clarity
Would this solution and delivery land well with a real customer?


📅 Submission & Mock Presentation
You’ll present your solution in a 1-hour mock call with 2–3 Atlanians playing customer stakeholders.
Format:
5 min – Intros


5 min – How you approached the challenge


30–40 min – Walkthrough of your solution (deck + code)


10 min – Feedback and wrap-up


Please send your deliverables at least one day in advance of your session.

☝️ Other Tips
Review Atlan’s public documentation to set proper expectations on what we can and cannot support during the Implementation.
Check out how we got started and the journey we’ve been on for the past several years
Check out our Newsroom to see what’s been going on lately


❤️ Final Notes
We know this is a time commitment — thank you.
This challenge is not about perfection — it’s about how you think, structure problems, and communicate solutions.
If you need more time, have questions, or want to bounce ideas — just reach out. We’re here to help and want this to be a delightful experience for you.
Good luck, and go be awesome.
We’re rooting for you. 🙌


