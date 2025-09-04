# System Diagrams - Bedrock Budgeteer

## Overview

This document contains visual representations of the Bedrock Budgeteer system architecture, data flows, and operational workflows. These diagrams provide a comprehensive view of how components interact and data flows through the system.

## System Architecture Diagram

The following diagram shows the complete system architecture with all major components and their relationships:

```mermaid
graph TB
    subgraph "User Interaction"
        U[User/API Key]
        BR[Bedrock API Calls]
    end
    
    subgraph "Event Ingestion Layer"
        CT[CloudTrail<br/>Multi-Region Trail]
        EB[EventBridge Rules<br/>bedrock-usage<br/>iam-key-creation<br/>iam-permissions]
        CWL[CloudWatch Logs<br/>Bedrock Invocation Logs]
        KF[Kinesis Firehose<br/>bedrock-usage-logs]
        S3B[S3 Bucket<br/>Log Storage]
    end
    
    subgraph "Core Processing Layer"
        US[User Setup Lambda<br/>Initialize Budgets]
        UC[Usage Calculator Lambda<br/>Real-time Cost Calculation]
        BM[Budget Monitor Lambda<br/>Threshold Evaluation]
        BR[Budget Refresh Lambda<br/>Periodic Reset]
        AL[Audit Logger Lambda<br/>Compliance Tracking]
        PM[Pricing Manager Lambda<br/>Price Cache Management]
    end
    
    subgraph "Data Storage Layer"
        UB[(UserBudgets Table<br/>Principal Budget Tracking)]
        UT[(UsageTracking Table<br/>Historical Usage Data)]
        AD[(AuditLogs Table<br/>System Audit Trail)]
        PR[(Pricing Table<br/>Model Price Cache)]
        SSM[SSM Parameters<br/>Configuration Store]
    end
    
    subgraph "Workflow Orchestration Layer"
        SF1[Suspension Workflow<br/>Step Functions]
        SF2[Restoration Workflow<br/>Step Functions]
        
        subgraph "Workflow Functions"
            IU[IAM Utilities<br/>Policy Management]
            GP[Grace Period<br/>Notifications]
            PB[Policy Backup<br/>Restore Point]
            RV[Restoration Validation<br/>Eligibility Check]
        end
    end
    
    subgraph "Monitoring &amp; Alerting Layer"
        SNS1[Operational Alerts<br/>SNS Topic]
        SNS2[Budget Alerts<br/>SNS Topic]
        SNS3[High Severity<br/>SNS Topic]
        
        subgraph "Notification Channels"
            EMAIL[Email<br/>Subscriptions]
            SLACK[Slack<br/>Webhook Integration]
            PD[PagerDuty<br/>Critical Alerts]
            SMS[SMS<br/>High Priority]
        end
        
        subgraph "Observability"
            CWD[CloudWatch<br/>Dashboards]
            CWA[CloudWatch<br/>Alarms]
            CWM[Custom<br/>Metrics]
        end
    end
    
    subgraph "External Services"
        PRICING[AWS Pricing API<br/>Real-time Model Costs]
        IAM[AWS IAM<br/>Access Control]
        BEDROCK[AWS Bedrock<br/>Foundation Models]
    end
    
    %% User flow
    U --> BR
    BR --> BEDROCK
    
    %% Ingestion flow
    BEDROCK --> CWL
    BEDROCK --> CT
    CT --> EB
    CWL --> KF
    KF --> S3B
    KF --> UC
    
    %% Event routing
    EB --> US
    EB --> PM
    EB --> AL
    
    %% Processing flow
    US --> UB
    UC --> UB
    UC --> UT
    UC --> PRICING
    BM --> UB
    BR --> UB
    AL --> AD
    PM --> PR
    PM --> PRICING
    
    %% Configuration
    US --> SSM
    UC --> SSM
    BM --> SSM
    BR --> SSM
    
    %% Workflow triggers
    BM --> SF1
    BR --> SF2
    
    %% Workflow execution
    SF1 --> IU
    SF1 --> GP
    SF1 --> PB
    SF2 --> IU
    SF2 --> RV
    
    %% IAM operations
    IU --> IAM
    PB --> IAM
    RV --> IAM
    
    %% Notifications
    SF1 --> SNS3
    SF2 --> SNS1
    BM --> SNS2
    GP --> SNS1
    
    %% Notification delivery
    SNS1 --> EMAIL
    SNS1 --> SLACK
    SNS2 --> EMAIL
    SNS2 --> SLACK
    SNS3 --> EMAIL
    SNS3 --> SLACK
    SNS3 --> PD
    SNS3 --> SMS
    
    %% Monitoring
    SNS1 --> CWA
    SNS2 --> CWA
    SNS3 --> CWA
    US --> CWM
    UC --> CWM
    BM --> CWM
    CWA --> CWD
    CWM --> CWD
    
    %% Styling
    classDef userClass fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef ingestionClass fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef processingClass fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef storageClass fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef workflowClass fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef monitoringClass fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    classDef externalClass fill:#f1f8e9,stroke:#33691e,stroke-width:2px
    
    class U,BR userClass
    class CT,EB,CWL,KF,S3B ingestionClass
    class US,UC,BM,BR,AL,PM processingClass
    class UB,UT,AD,PR,SSM storageClass
    class SF1,SF2,IU,GP,PB,RV workflowClass
    class SNS1,SNS2,SNS3,EMAIL,SLACK,PD,SMS,CWD,CWA,CWM monitoringClass
    class PRICING,IAM,BEDROCK externalClass
```

## Complete User Journey Sequence

This sequence diagram shows the complete user journey from API key creation to budget violation handling:

```mermaid
sequenceDiagram
    participant User
    participant Bedrock
    participant CloudTrail
    participant EventBridge
    participant UserSetup as User Setup Lambda
    participant PricingMgr as Pricing Manager
    participant CloudWatch as CloudWatch Logs
    participant Firehose as Kinesis Firehose
    participant UsageCalc as Usage Calculator
    participant DynamoDB
    participant BudgetMonitor as Budget Monitor
    participant StepFunctions as Step Functions
    participant IAM
    participant SNS
    
    Note over User,SNS: Complete User Journey - From API Key Creation to Budget Violation
    
    rect rgb(240, 248, 255)
        Note over User,DynamoDB: 1. User/API Key Creation
        User->>CloudTrail: Create Bedrock API Key
        CloudTrail->>EventBridge: CreateUser Event
        EventBridge->>UserSetup: Trigger User Setup
        EventBridge->>PricingMgr: Trigger Pricing Population
        
        par User Setup
            UserSetup->>DynamoDB: Initialize User Budget
            UserSetup->>DynamoDB: Set Default Limits ($1)
        and Pricing Setup
            PricingMgr->>DynamoDB: Populate Model Pricing
            Note over PricingMgr: First API key triggers pricing cache population
        end
    end
    
    rect rgb(245, 255, 245)
        Note over User,DynamoDB: 2. Real-time Usage Processing
        User->>Bedrock: InvokeModel Request
        Bedrock->>CloudWatch: Write Invocation Log
        CloudWatch->>Firehose: Stream Log Event
        Firehose->>UsageCalc: Transform and Process
        
        UsageCalc->>DynamoDB: Get Model Pricing
        UsageCalc->>DynamoDB: Calculate Token Cost
        UsageCalc->>DynamoDB: Update User Budget
        Note over UsageCalc,DynamoDB: Real-time budget tracking
    end
    
    rect rgb(255, 245, 245)
        Note over BudgetMonitor,SNS: 3. Budget Monitoring and Violation Response
        
        loop Every 5 minutes
            BudgetMonitor->>DynamoDB: Scan User Budgets
            BudgetMonitor->>BudgetMonitor: Check Thresholds
            
            alt Budget Exceeded (100%+)
                BudgetMonitor->>DynamoDB: Start Grace Period
                BudgetMonitor->>EventBridge: Publish Suspension Event
                EventBridge->>StepFunctions: Trigger Workflow
                
                StepFunctions->>SNS: Send Grace Notification
                Note over StepFunctions: Wait Grace Period (5 minutes default)
                StepFunctions->>SNS: Send Final Warning
                StepFunctions->>IAM: Apply Full Suspension
                StepFunctions->>DynamoDB: Update Status to Suspended
                StepFunctions->>SNS: Send Audit Event
                
            else Warning Threshold (70%+)
                BudgetMonitor->>SNS: Send Warning Alert
            else Critical Threshold (90%+)
                BudgetMonitor->>SNS: Send Critical Alert
            end
        end
    end
    
    rect rgb(248, 255, 248)
        Note over BudgetMonitor,SNS: 4. Automatic Restoration (Budget Refresh)
        
        Note over BudgetMonitor: Daily at 2 AM UTC
        BudgetMonitor->>DynamoDB: Check Refresh Dates
        
        alt Refresh Period Reached
            BudgetMonitor->>EventBridge: Publish Restoration Event
            EventBridge->>StepFunctions: Trigger Restoration
            
            StepFunctions->>StepFunctions: Validate Restoration
            StepFunctions->>IAM: Restore Full Access
            StepFunctions->>DynamoDB: Reset Budget Status
            StepFunctions->>DynamoDB: Reset spent_usd = 0
            StepFunctions->>SNS: Send Restoration Alert
        end
    end
    
    rect rgb(255, 248, 240)
        Note over DynamoDB,SNS: 5. Continuous System Monitoring
        
        loop Continuous
            Note over DynamoDB,SNS: CloudWatch Metrics and Alarms
            DynamoDB-->>SNS: High Error Rate Alert
            UsageCalc-->>SNS: Function Failure Alert
            StepFunctions-->>SNS: Workflow Failure Alert
        end
    end
```

## Workflow Processing Logic

This diagram shows the detailed logic flow for budget monitoring, suspension, and restoration workflows:

```mermaid
graph TD
    subgraph "Suspension Workflow"
        SW_START[Workflow Start<br/>Budget Exceeded Event]
        SW_GRACE[Send Grace Period<br/>Notification]
        SW_WAIT[Grace Period Wait<br/>Configurable Duration]
        SW_FINAL[Send Final Warning<br/>Notification]
        SW_SUSPEND[Apply Full Suspension<br/>Detach IAM Policies]
        SW_UPDATE[Update User Status<br/>Set status = suspended]
        SW_AUDIT[Send Audit Event<br/>Log Suspension Action]
        SW_SUCCESS[Suspension Complete<br/>Success]
        SW_ERROR[Suspension Failed<br/>Send to DLQ]
        
        SW_START --> SW_GRACE
        SW_GRACE --> SW_WAIT
        SW_WAIT --> SW_FINAL
        SW_FINAL --> SW_SUSPEND
        SW_SUSPEND --> SW_UPDATE
        SW_UPDATE --> SW_AUDIT
        SW_AUDIT --> SW_SUCCESS
        
        SW_GRACE -.->|Error| SW_ERROR
        SW_SUSPEND -.->|Error| SW_ERROR
        SW_UPDATE -.->|Error| SW_ERROR
    end
    
    subgraph "Restoration Workflow"
        RW_START[Workflow Start<br/>Restoration Event]
        RW_VALIDATE[Validate Restoration<br/>Check Eligibility]
        RW_CHOICE{Validation<br/>Passed?}
        RW_RESTORE[Restore Access<br/>Re-attach IAM Policies]
        RW_VERIFY[Validate Restoration<br/>Confirm Access]
        RW_RESET[Reset Budget Status<br/>Clear spent amount]
        RW_AUDIT[Send Audit Event<br/>Log Restoration Action]
        RW_SUCCESS[Restoration Complete<br/>Success]
        RW_SKIP[Skip Restoration<br/>Not Eligible]
        RW_ERROR[Restoration Failed<br/>Send to DLQ]
        
        RW_START --> RW_VALIDATE
        RW_VALIDATE --> RW_CHOICE
        RW_CHOICE -->|Yes| RW_RESTORE
        RW_CHOICE -->|No| RW_SKIP
        RW_RESTORE --> RW_VERIFY
        RW_VERIFY --> RW_RESET
        RW_RESET --> RW_AUDIT
        RW_AUDIT --> RW_SUCCESS
        
        RW_VALIDATE -.->|Error| RW_ERROR
        RW_RESTORE -.->|Error| RW_ERROR
        RW_RESET -.->|Error| RW_ERROR
    end
    
    subgraph "Budget Monitoring Logic"
        BM_START[Monitor Start<br/>Scheduled Trigger]
        BM_SCAN[Scan User Budgets<br/>Check All Users]
        BM_CALC[Calculate Usage<br/>spent_usd / budget_limit_usd]
        BM_CHECK{Budget<br/>Status?}
        BM_NORMAL[Normal Usage<br/>< 70%]
        BM_WARN[Warning Level<br/>70% - 89%]
        BM_CRITICAL[Critical Level<br/>90% - 99%]
        BM_EXCEEDED[Budget Exceeded<br/>>= 100%]
        BM_GRACE{In Grace<br/>Period?}
        BM_START_GRACE[Start Grace Period<br/>Set grace deadline]
        BM_CHECK_GRACE[Check Grace Expiry<br/>Current time vs deadline]
        BM_EXPIRED{Grace<br/>Expired?}
        BM_TRIGGER[Trigger Suspension<br/>Workflow]
        BM_WAIT[Wait for Grace<br/>Period to Expire]
        BM_ALERT_WARN[Send Warning<br/>Notification]
        BM_ALERT_CRIT[Send Critical<br/>Notification]
        BM_CONTINUE[Continue<br/>Monitoring]
        
        BM_START --> BM_SCAN
        BM_SCAN --> BM_CALC
        BM_CALC --> BM_CHECK
        BM_CHECK -->|< 70%| BM_NORMAL
        BM_CHECK -->|70-89%| BM_WARN
        BM_CHECK -->|90-99%| BM_CRITICAL
        BM_CHECK -->|>= 100%| BM_EXCEEDED
        
        BM_NORMAL --> BM_CONTINUE
        BM_WARN --> BM_ALERT_WARN
        BM_CRITICAL --> BM_ALERT_CRIT
        BM_ALERT_WARN --> BM_CONTINUE
        BM_ALERT_CRIT --> BM_CONTINUE
        
        BM_EXCEEDED --> BM_GRACE
        BM_GRACE -->|No| BM_START_GRACE
        BM_GRACE -->|Yes| BM_CHECK_GRACE
        BM_START_GRACE --> BM_WAIT
        BM_CHECK_GRACE --> BM_EXPIRED
        BM_EXPIRED -->|No| BM_WAIT
        BM_EXPIRED -->|Yes| BM_TRIGGER
        BM_WAIT --> BM_CONTINUE
        BM_TRIGGER --> SW_START
        
        BM_CONTINUE --> BM_START
    end
    
    subgraph "Data Flow"
        DF_BEDROCK[Bedrock API<br/>Usage Event]
        DF_LOG[CloudWatch<br/>Invocation Log]
        DF_FIREHOSE[Kinesis Firehose<br/>Stream Processing]
        DF_CALC[Usage Calculator<br/>Cost Calculation]
        DF_UPDATE[DynamoDB Update<br/>spent_usd += cost]
        DF_MONITOR[Budget Monitor<br/>Threshold Check]
        
        DF_BEDROCK --> DF_LOG
        DF_LOG --> DF_FIREHOSE
        DF_FIREHOSE --> DF_CALC
        DF_CALC --> DF_UPDATE
        DF_UPDATE --> DF_MONITOR
        DF_MONITOR --> BM_START
    end
    
    %% Connect workflows to monitoring
    BM_TRIGGER --> SW_START
    
    %% Restoration trigger (from Budget Refresh Lambda)
    RW_START -.->|Daily Check| RW_VALIDATE
    
    %% Styling
    classDef suspensionClass fill:#ffebee,stroke:#c62828,stroke-width:2px
    classDef restorationClass fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef monitoringClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef dataClass fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef errorClass fill:#fce4ec,stroke:#ad1457,stroke-width:2px
    classDef decisionClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    
    class SW_START,SW_GRACE,SW_WAIT,SW_FINAL,SW_SUSPEND,SW_UPDATE,SW_AUDIT,SW_SUCCESS suspensionClass
    class RW_START,RW_VALIDATE,RW_RESTORE,RW_VERIFY,RW_RESET,RW_AUDIT,RW_SUCCESS,RW_SKIP restorationClass
    class BM_START,BM_SCAN,BM_CALC,BM_NORMAL,BM_WARN,BM_CRITICAL,BM_EXCEEDED,BM_START_GRACE,BM_CHECK_GRACE,BM_WAIT,BM_ALERT_WARN,BM_ALERT_CRIT,BM_CONTINUE,BM_TRIGGER monitoringClass
    class DF_BEDROCK,DF_LOG,DF_FIREHOSE,DF_CALC,DF_UPDATE,DF_MONITOR dataClass
    class SW_ERROR,RW_ERROR errorClass
    class BM_CHECK,BM_GRACE,BM_EXPIRED,RW_CHOICE decisionClass
```

## Data Storage Schema

The following diagram shows the DynamoDB table structure and relationships:

```mermaid
erDiagram
    UserBudgets ||--o{ UsageTracking : "principal_id"
    UserBudgets ||--o{ AuditLogs : "user_identity"
    
    UserBudgets {
        string principal_id PK
        number budget_limit_usd
        number spent_usd
        string status
        string account_type
        string budget_period_start
        string budget_refresh_date
        number grace_deadline_epoch
        string threshold_state
        number refresh_period_days
        number refresh_count
        string created_at
        string last_updated
    }
    
    UsageTracking {
        string principal_id PK
        string timestamp SK
        string service_name
        number cost_usd
        number input_tokens
        number output_tokens
        string model_id
        string region
        string request_id
    }
    
    AuditLogs {
        string event_id PK
        string event_time SK
        string event_source
        string event_type
        string user_identity
        string details
        number timestamp_epoch
    }
    
    Pricing {
        string model_id PK
        string region SK
        number input_tokens_per_1000
        number output_tokens_per_1000
        string last_updated
        string data_source
        number ttl
    }
```

## Monitoring and Alerting Flow

This diagram shows how monitoring data flows through the system and triggers alerts:

```mermaid
graph LR
    subgraph "Metric Sources"
        L1[Lambda Functions]
        L2[DynamoDB Tables]
        L3[Step Functions]
        L4[EventBridge Rules]
        L5[Firehose Streams]
        L6[Custom Business Metrics]
    end
    
    subgraph "CloudWatch"
        M1[Standard Metrics]
        M2[Custom Metrics]
        A1[Lambda Error Alarms]
        A2[DynamoDB Throttle Alarms]
        A3[Step Functions Failure Alarms]
        A4[Business KPI Alarms]
    end
    
    subgraph "SNS Topics"
        S1[Operational Alerts]
        S2[Budget Alerts]
        S3[High Severity]
    end
    
    subgraph "Notification Channels"
        N1[Email]
        N2[Slack]
        N3[PagerDuty]
        N4[SMS]
        N5[Webhook]
    end
    
    subgraph "Dashboards"
        D1[System Overview]
        D2[Ingestion Pipeline]
        D3[Workflow Orchestration]
        D4[Business Metrics]
    end
    
    L1 --> M1
    L2 --> M1
    L3 --> M1
    L4 --> M1
    L5 --> M1
    L6 --> M2
    
    M1 --> A1
    M1 --> A2
    M1 --> A3
    M2 --> A4
    
    A1 --> S1
    A1 --> S3
    A2 --> S1
    A3 --> S3
    A4 --> S2
    A4 --> S3
    
    S1 --> N1
    S1 --> N2
    S2 --> N1
    S2 --> N2
    S3 --> N1
    S3 --> N2
    S3 --> N3
    S3 --> N4
    S3 --> N5
    
    M1 --> D1
    M1 --> D2
    M1 --> D3
    M2 --> D4
    
    classDef sourceClass fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef metricClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef alarmClass fill:#ffebee,stroke:#c62828,stroke-width:2px
    classDef topicClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef notifyClass fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef dashClass fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    
    class L1,L2,L3,L4,L5,L6 sourceClass
    class M1,M2 metricClass
    class A1,A2,A3,A4 alarmClass
    class S1,S2,S3 topicClass
    class N1,N2,N3,N4,N5 notifyClass
    class D1,D2,D3,D4 dashClass
```

## Network and Security Architecture

This diagram shows the security boundaries and data flow within AWS:

```mermaid
graph TB
    subgraph "AWS Account"
        subgraph "IAM Security"
            IR1[Lambda Execution Role]
            IR2[Step Functions Role]
            IR3[EventBridge Role]
            IR4[Bedrock Logging Role]
            IP1[DynamoDB Access Policy]
            IP2[S3 Access Policy]
            IP3[EventBridge Publish Policy]
        end
        
        subgraph "VPC (Optional)"
            VPC[VPC Endpoints<br/>for DynamoDB/S3]
        end
        
        subgraph "Encryption"
            KMS[Customer Managed<br/>KMS Key]
            E1[DynamoDB Encryption]
            E2[S3 Encryption]
            E3[CloudWatch Encryption]
            E4[SNS Encryption]
        end
        
        subgraph "Application Layer"
            AL[Lambda Functions<br/>Step Functions<br/>EventBridge Rules]
        end
        
        subgraph "Data Layer"
            DL[DynamoDB Tables<br/>S3 Buckets<br/>CloudWatch Logs]
        end
        
        subgraph "External Access"
            CT[CloudTrail Events]
            BR[Bedrock API Calls]
            PR[Pricing API Calls]
        end
    end
    
    subgraph "External Services"
        EXT1[Email Providers]
        EXT2[Slack Webhook]
        EXT3[PagerDuty API]
        EXT4[SMS Providers]
    end
    
    %% IAM relationships
    IR1 --> AL
    IR2 --> AL
    IR3 --> AL
    IR4 --> BR
    
    IP1 --> DL
    IP2 --> DL
    IP3 --> AL
    
    %% Encryption relationships
    KMS --> E1
    KMS --> E2
    KMS --> E3
    KMS --> E4
    
    E1 --> DL
    E2 --> DL
    E3 --> DL
    E4 --> AL
    
    %% Data flow
    AL --> DL
    CT --> AL
    BR --> AL
    AL --> PR
    
    %% External communication
    AL --> EXT1
    AL --> EXT2
    AL --> EXT3
    AL --> EXT4
    
    %% Optional VPC
    AL -.-> VPC
    VPC -.-> DL
    
    classDef iamClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef encryptClass fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef appClass fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef dataClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef extClass fill:#ffebee,stroke:#c62828,stroke-width:2px
    classDef vpcClass fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    
    class IR1,IR2,IR3,IR4,IP1,IP2,IP3 iamClass
    class KMS,E1,E2,E3,E4 encryptClass
    class AL appClass
    class DL dataClass
    class CT,BR,PR,EXT1,EXT2,EXT3,EXT4 extClass
    class VPC vpcClass
```

## Cost Flow and Calculation

This diagram shows how costs are calculated and tracked through the system:

```mermaid
graph TD
    subgraph "Cost Calculation Flow"
        API[Bedrock API Call<br/>InvokeModel Request]
        LOG[Invocation Log<br/>Input/Output Tokens]
        STREAM[Firehose Stream<br/>Real-time Processing]
        CALC[Usage Calculator<br/>Cost Computation]
        
        subgraph "Pricing Data"
            CACHE[Pricing Cache<br/>DynamoDB Table]
            PRICING_API[AWS Pricing API<br/>Real-time Rates]
            FALLBACK[Fallback Pricing<br/>Static Rates]
        end
        
        subgraph "Cost Computation"
            INPUT_COST[Input Token Cost<br/>tokens × rate_per_1000]
            OUTPUT_COST[Output Token Cost<br/>tokens × rate_per_1000]
            TOTAL_COST[Total Request Cost<br/>input_cost + output_cost]
        end
        
        subgraph "Budget Update"
            CURRENT[Current Budget<br/>spent_usd]
            UPDATE[Update Budget<br/>spent_usd += total_cost]
            THRESHOLD[Check Thresholds<br/>spent_usd / budget_limit_usd]
        end
        
        API --> LOG
        LOG --> STREAM
        STREAM --> CALC
        
        CALC --> CACHE
        CACHE -->|Cache Miss| PRICING_API
        PRICING_API -->|API Failure| FALLBACK
        
        CALC --> INPUT_COST
        CALC --> OUTPUT_COST
        INPUT_COST --> TOTAL_COST
        OUTPUT_COST --> TOTAL_COST
        
        TOTAL_COST --> CURRENT
        CURRENT --> UPDATE
        UPDATE --> THRESHOLD
        
        THRESHOLD -->|>= 100%| VIOLATION[Budget Violation<br/>Trigger Suspension]
        THRESHOLD -->|>= 90%| WARNING[Critical Warning<br/>Send Alert]
        THRESHOLD -->|>= 70%| WARN[Budget Warning<br/>Send Notification]
        THRESHOLD -->|< 70%| NORMAL[Normal Usage<br/>Continue Monitoring]
    end
    
    classDef apiClass fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef processingClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef pricingClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef calcClass fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef budgetClass fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    classDef alertClass fill:#ffebee,stroke:#c62828,stroke-width:2px
    
    class API,LOG,STREAM apiClass
    class CALC processingClass
    class CACHE,PRICING_API,FALLBACK pricingClass
    class INPUT_COST,OUTPUT_COST,TOTAL_COST calcClass
    class CURRENT,UPDATE,THRESHOLD budgetClass
    class VIOLATION,WARNING,WARN,NORMAL alertClass
```

## Diagram Legend

### Color Coding

- **Blue (User/API)**: User interactions and API calls
- **Purple (Ingestion)**: Event ingestion and data collection
- **Green (Processing)**: Core processing and business logic
- **Orange (Storage)**: Data storage and persistence
- **Pink (Workflow)**: Workflow orchestration and automation
- **Teal (Monitoring)**: Monitoring, alerting, and observability
- **Light Green (External)**: External services and APIs

### Symbol Meanings

- **Rectangles**: Services, functions, and components
- **Cylinders**: Data stores (DynamoDB, S3)
- **Diamonds**: Decision points and conditions
- **Circles**: Start/end points
- **Dashed Lines**: Error paths and fallback flows
- **Solid Lines**: Normal data flow
- **Dotted Lines**: Optional or conditional flows

### Component Types

- **Lambda Functions**: Serverless compute units
- **Step Functions**: Workflow orchestration
- **DynamoDB**: NoSQL database tables
- **EventBridge**: Event routing service
- **SNS**: Notification service
- **CloudWatch**: Monitoring and logging
- **S3**: Object storage for logs
- **Kinesis Firehose**: Data streaming service

These diagrams provide a comprehensive visual reference for understanding the Bedrock Budgeteer system architecture, data flows, and operational patterns.
