# AutoExpensify
At SeatGeek, employees are given a monthly allowance to be spent on events on the website.  Employees make the purchases themselves, and then submit receipts to be reimbursed through the Expensify app.  While Expensify has a remarkable ability to ingest emails sent to receipts@expensify.com, it's not always fast or accurate.  I wanted to make a system that worked fast and very well, for the specific SeatGeek use case.

AutoExpensify is a Python script that runs on AWS' serverless Lambda service.  Lambda is great, because it has no overhead and scales seamlessly.  Receipts tend to be congregated at the end of the month.  With the Lambda reaction-based architecture, you're not paying for 90% of the month with very little traffic only to have high traffic throttled at the end of the month.

Autoexpensify uses several AWS other offerings, including SES for email routing, S3 for message storage, DynamoDB for database calls, and CloudWatch for monitoring.

# Setup
There are several steps to setting this up.  I'm no sysadmin, so a lot of this was new to me.

## 1. Configure email routing

## 2. Establish SES rules and configure S3 storage

## 3. Configure DynamoDB

## 4. Configure Lambda and Deploy Code

`lambda_s3_dynamodb_exec_role`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Stmt1428341300017",
      "Action": [
        "dynamodb:DeleteItem",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem"
      ],
      "Effect": "Allow",
      "Resource": "*"
    },
    {
      "Sid": "",
      "Resource": "*",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Effect": "Allow"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::*"
      ]
    }
  ]
}
```
