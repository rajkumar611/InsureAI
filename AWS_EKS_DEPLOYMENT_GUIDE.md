# AWS EKS Deployment Guide — InsureAI

**Date:** 2026-05-31  
**Project:** InsureAI (Multi-agent AI insurance underwriting platform)  
**Target:** Deploy to AWS EKS (Elastic Kubernetes Service) in Asia Pacific (Sydney)

---

## Overview

This guide documents the complete process of deploying InsureAI to AWS EKS, including:
- AWS account & IAM setup
- ECR (container registry) creation
- EKS cluster provisioning
- Worker node setup
- kubectl configuration
- K8s manifest deployment

**Key Learning:** Switched from Azure AKS to AWS EKS mid-project due to free tier availability.

---

## Prerequisites

- AWS free tier account (fresh, with $200 credits + 12-month free tier)
- AWS CLI installed locally
- kubectl installed locally
- Docker installed locally
- Git repo with K8s manifests and Dockerfile

---

## Phase 1: AWS Account Setup

### Step 1: Create AWS Free Tier Account

**Location:** https://aws.amazon.com/free/

**Action:** Sign up with new email address (each email gets fresh $200 credits + 12-month free tier)

**Result:** Fresh AWS account with Account ID `257212470251`

---

## Phase 2: AWS CLI & Credentials

### Step 2: Install AWS CLI

**Windows:** Download MSI installer from https://awscli.amazonaws.com/AWSCLIV2.msi

**After install:**
```powershell
# Verify installation
aws --version

# If not found, add to PATH
$env:Path += ";C:\Program Files\Amazon\AWSCLIV2"
aws --version  # Should show version
```

**Result:** AWS CLI v2.34.57 installed and accessible

### Step 3: Create IAM User for Programmatic Access

**Why:** Need access keys (Access Key ID + Secret) to run AWS CLI commands and authenticate GitHub Actions

**AWS Console Path:**
1. IAM → Users → Create user
2. Username: `rajaiaskb`
3. **Skip** "Provide user access to AWS Management Console" (we only need CLI access)
4. Attach policies:
   - ✓ AmazonEC2ContainerRegistryFullAccess (for ECR)
   - ✓ AmazonEC2FullAccess (for EC2 + general compute)
   - ⚠️ Note: EKS-specific policies not available in free tier

**Result:** IAM user created with permissions

### Step 4: Generate Access Keys

**AWS Console Path:**
1. IAM → Users → rajaiaskb → Create access key
2. Use case: **Command Line Interface (CLI)**
3. Save:
   - Access Key ID
   - Secret Access Key

**CRITICAL:** Save these securely—you won't see them again!

### Step 5: Configure AWS CLI

**PowerShell:**
```powershell
aws configure
```

**Prompts:**
- AWS Access Key ID: [from Step 4]
- AWS Secret Access Key: [from Step 4]
- Default region: `us-east-1` (will be overridden later)
- Output format: `json`

**Result:** AWS CLI authenticated to your account

---

## Phase 3: Container Registry (ECR)

### Step 6: Create ECR Repository

**Purpose:** Store Docker images for EKS to pull

**Command:**
```powershell
aws ecr create-repository --repository-name insureai --region us-east-1
```

**Output:**
```json
{
  "repository": {
    "repositoryUri": "257212470251.dkr.ecr.us-east-1.amazonaws.com/insureai",
    ...
  }
}
```

**Result:** ECR repository created at `257212470251.dkr.ecr.us-east-1.amazonaws.com/insureai`

**Note:** Image will be pushed here by GitHub Actions (or manually via `docker push`)

---

## Phase 4: EKS Cluster Creation

### Step 7: Create IAM Role for EKS Service

**Purpose:** EKS control plane needs permission to manage AWS resources

**AWS Console Path:**
1. IAM → Roles → Create role
2. Select "AWS service" → Search "EKS" → Select it
3. Attach policy: `AmazonEKSServiceRolePolicy` (auto-selected)
4. Name: `eksServiceRole`
5. Create

**Result:** IAM role `eksServiceRole` created with EKS permissions

### Step 8: Create EKS Cluster

**AWS Console Path:**
1. Search "EKS" → Clusters → Create cluster
2. **Cluster name:** `insureai-eks`
3. **Kubernetes version:** `1.35` (latest available)
4. **Cluster IAM role:** `eksServiceRole` (created in Step 7)
5. **VPC:** Default VPC (auto-selected)
6. **Subnets:** Default subnets (auto-selected)
7. Create cluster

**⏱️ Wait:** Cluster takes ~10 minutes to reach "Active" state

**Result:**
```
Status: Active ✓
Kubernetes version: 1.35
Region: Asia Pacific (Sydney) = ap-southeast-2
```

**⚠️ GOTCHA:** Cluster created in **ap-southeast-2** (Sydney) instead of us-east-1!
- Reason: Free tier account regional default
- Fix: Use `--region ap-southeast-2` in all subsequent commands

### Step 9: Worker Nodes (Auto-Provisioned)

**AWS Console:** EKS → Clusters → insureai-eks → Compute tab

**Observation:**
- 2 worker nodes auto-created: `i-0c461e6876940a409`, `i-0f2541e8084f08152`
- Instance type: `c7i-flex.large`
- Status: Ready ✓
- Created automatically by AWS EKS

**Result:** Cluster has 2 healthy worker nodes ready for pod deployment

---

## Phase 5: kubectl Configuration

### Step 10: Connect kubectl to EKS Cluster

**Challenge:** IAM user lacked EKS permissions in free tier

**Solution:** Use AWS CloudShell (browser-based terminal with proper permissions)

**CloudShell Command:**
```bash
aws eks update-kubeconfig --name insureai-eks --region ap-southeast-2
```

**Output:**
```
Added new context arn:aws:eks:ap-southeast-2:257212470251:cluster/insureai-eks to /home/cloudshell-user/.kube/config
```

**Result:** kubectl configured to connect to insureai-eks cluster

### Step 11: Verify kubectl Connection

**Command:**
```bash
kubectl get nodes
```

**Output:**
```
NAME                           STATUS   ROLES    AGE   VERSION
ip-172-31-0-XXX.ec2.internal   Ready    <none>   5m    v1.35.x
ip-172-31-1-XXX.ec2.internal   Ready    <none>   5m    v1.35.x
```

**Result:** kubectl successfully communicates with EKS cluster ✓

---

## Phase 6: Kubernetes Manifests Deployment

### Step 12: Create Namespace

**Command (in CloudShell):**
```bash
cat > namespace.yaml << 'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: insureai
  labels:
    name: insureai
EOF
```

**Status:** [IN PROGRESS — Continue from here]

### Step 13: Create ConfigMap

**Status:** [PENDING]

### Step 14: Create Secret

**Status:** [PENDING]
- Requires: ANTHROPIC_API_KEY, POSTGRES_PASSWORD, DATABASE_URL
- Method: kubectl create secret or YAML

### Step 15: Deploy PostgreSQL StatefulSet

**Status:** [PENDING]

### Step 16: Deploy FastAPI Deployment

**Status:** [PENDING]

### Step 17: Deploy Streamlit Deployment

**Status:** [PENDING]

---

## Key Challenges & Solutions

| Challenge | Root Cause | Solution |
|-----------|-----------|----------|
| AWS CLI not in PATH after install | Installer didn't register in system PATH | Manually added to `$env:Path` in PowerShell |
| IAM user lacked EKS permissions | Free tier IAM policies limited | Used AWS CloudShell (has root permissions) |
| `aws eks update-kubeconfig` failed with "No cluster found" | Cluster in ap-southeast-2, but command used us-east-1 | Updated region to ap-southeast-2 |
| AmazonEKSFullAccess policy not found in IAM | Free tier limited policy list | Proceeded with EC2FullAccess (covers most needs) |
| EKS cluster creation seemed slow | Normal: control plane init + node provisioning takes 10 min | Waited for "Active" status before proceeding |

---

## Architecture Summary

```
AWS Region: Asia Pacific (Sydney) [ap-southeast-2]
│
├─ EKS Cluster: insureai-eks
│  ├─ Control Plane (Managed by AWS)
│  │  └─ Kubernetes 1.35
│  │
│  ├─ Worker Nodes: 2x c7i-flex.large
│  │
│  └─ Namespace: insureai
│     ├─ ConfigMap: insureai-config
│     ├─ Secret: insureai-secrets
│     ├─ StatefulSet: postgres-0
│     ├─ Deployment: insureai-api (2 replicas)
│     └─ Deployment: insureai-dashboard (1 replica)
│
├─ ECR Repository: insureai
│  └─ Stores Docker images for deployments
│
└─ IAM User: rajaiaskb
   └─ Access keys for AWS CLI + GitHub Actions
```

---

## GitHub Actions Integration

**File:** `.github/workflows/deploy.yml`

**Updated for AWS:**
- Changed from Azure ACR → AWS ECR
- Changed from Azure login → AWS credentials
- CloudShell uses `aws eks update-kubeconfig` before kubectl deploy

**Secrets needed in GitHub:**
```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
EKS_CLUSTER_NAME = insureai-eks
AWS_REGION = ap-southeast-2
ECR_REPOSITORY = insureai
```

---

## Interview Talking Points

1. **Cloud Platform Choice:**
   - "Started with Azure but found free tier limitations"
   - "Switched to AWS EKS for better free tier + mature K8s support"
   - "Demonstrated flexibility in cloud platform selection"

2. **Infrastructure as Code:**
   - "Created 6 K8s YAML manifests (namespace, configmap, secrets, postgres, API, dashboard)"
   - "K8s manifests are cloud-agnostic—same YAML works on any K8s"
   - "GitHub Actions automates build → push to ECR → deploy to EKS"

3. **Troubleshooting:**
   - "Diagnosed region mismatch (ap-southeast-2 vs us-east-1)"
   - "Used AWS CloudShell to work around IAM permission limitations"
   - "Understood K8s networking: headless services, ClusterIP routing, LoadBalancer exposure"

4. **Production Readiness:**
   - "2 API replicas for redundancy"
   - "Liveness & readiness probes for health checks"
   - "StatefulSet with persistent volume for Postgres"
   - "Secrets encrypted at rest in K8s etcd"

---

## Next Steps (To Complete)

- [ ] Apply K8s manifests in CloudShell
- [ ] Verify pods are running
- [ ] Get LoadBalancer external IPs
- [ ] Test API health check (curl)
- [ ] Test Streamlit dashboard (browser)
- [ ] Document final validation screenshots
- [ ] Update GitHub Actions secrets for ap-southeast-2
- [ ] Test CI/CD: push code → auto-deploy to EKS

---

## Useful Commands Reference

```bash
# CloudShell

# Check cluster status
kubectl get nodes
kubectl get pods -n insureai
kubectl get svc -n insureai

# View pod logs
kubectl logs -n insureai POD_NAME

# Port-forward for local testing
kubectl port-forward -n insureai svc/insureai-api 8081:80

# Delete deployment
kubectl delete deployment insureai-api -n insureai

# View all resources in namespace
kubectl get all -n insureai
```

---

**Last Updated:** 2026-05-31 (In Progress)  
**Status:** Deploying K8s manifests → Testing → Production

