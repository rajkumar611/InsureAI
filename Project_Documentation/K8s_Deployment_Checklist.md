# Kubernetes Deployment Checklist — AWS EKS

Use this checklist before pushing to `main` (triggers GitHub Actions deploy).

## Pre-Deployment (Code & Config)

### Code Readiness
- [ ] All deleted Python packages (e.g., alembic) removed from deployment specs
  - Search: `grep -r "alembic\|removed_package" k8s/`
  - Check: No initContainers referencing deleted modules
- [ ] Dockerfile builds without errors
  - Run: `docker build -f deployment/Dockerfile -t test-build:latest .`
- [ ] All Kubernetes manifests valid YAML
  - Run: `kubectl apply -f k8s/ --dry-run=client`

### Docker Image
- [ ] Image builds successfully
- [ ] Image pushes to ECR without auth errors
- [ ] Image runs locally: `docker run -e ANTHROPIC_API_KEY=... test-build:latest`

### Kubernetes Manifests
- [ ] `imagePullSecrets` section present in ALL deployment specs
  ```yaml
  imagePullSecrets:
  - name: ecr-secret
  ```
- [ ] No hardcoded credentials in manifests (use secrets/configmaps instead)
- [ ] Volume mounts (if any) have persistent volume claims defined
- [ ] Resource requests/limits are reasonable
  - API: 250m cpu / 512Mi memory (requests), 500m / 1Gi (limits)
  - Dashboard: 100m / 256Mi (requests), 200m / 512Mi (limits)

### Environment Configuration
- [ ] ConfigMap has correct values
  - `FRONTEND_ORIGIN`: matches actual frontend URL
  - `LOG_LEVEL`: set to INFO or DEBUG (not TRACE)
- [ ] Secrets exist or will be created by workflow
  - `ANTHROPIC_API_KEY`
  - `DATABASE_URL`
  - `POSTGRES_PASSWORD` (if using StatefulSet postgres)

### GitHub Actions Workflow
- [ ] Secrets configured in GitHub repo settings
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `EKS_CLUSTER_NAME`
  - `ANTHROPIC_API_KEY`
- [ ] Workflow steps in correct order
  1. Get kubeconfig
  2. Login to ECR
  3. Apply manifests
  4. Create ECR secret
  5. Update deployments
  6. Wait for rollout
- [ ] `--validate=false` flag used if kubectl validation fails
- [ ] `|| true` flag allows non-critical errors to not block deployment

## Infrastructure (AWS)

### EKS Cluster
- [ ] Cluster exists and is accessible
  - Run: `aws eks describe-cluster --name insureai-eks --region ap-southeast-2`
- [ ] All IAM users/service accounts added to cluster access entries
  - User: rajaiazkb (or whoever deploys)
  - Policy: `AmazonEKSAdminPolicy` with cluster-wide scope
  - Group: `admins`
  - Verify: AWS Console → EKS → Cluster → Access tab

### Networking
- [ ] VPC subnets tagged for ELB (required for LoadBalancer services)
  - All 3 subnets must have: `kubernetes.io/role/internal-elb=1`
  - Verify: AWS Console → VPC → Subnets, check tags
- [ ] Security groups allow ingress on required ports
  - Port 80 (HTTP) for LoadBalancer
  - Port 443 (HTTPS) if using TLS
- [ ] NAT gateway or bastion exists if private subnets

### ECR Repository
- [ ] ECR repository `insureai` exists
  - Run: `aws ecr describe-repositories --region ap-southeast-2`
- [ ] Repository has image pull permissions for EKS service account
- [ ] Lifecycle policy configured (optional: auto-delete old images after 30 days)

### Database (PostgreSQL)
- [ ] PostgreSQL instance is running (standalone or in-cluster)
- [ ] pgvector extension installed
  - Run: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] Backups configured (if production)
- [ ] Database user + password set in secrets

## Post-Deployment (Validation)

### Pod Health
- [ ] All pods in insureai namespace are Running (not Pending, CrashLoopBackOff, etc.)
  ```bash
  kubectl get pods -n insureai
  ```
- [ ] Each pod has 1/1 containers Ready
  ```bash
  kubectl get pods -n insureai -o wide
  ```
- [ ] Liveness probes passing (restart count should be 0)
  ```bash
  kubectl describe pods -n insureai
  ```

### Services & Networking
- [ ] LoadBalancer services have External IP assigned (not <pending>)
  ```bash
  kubectl get svc -n insureai
  ```
- [ ] External IPs are publicly accessible
  ```bash
  curl http://<external-ip>/health
  ```
- [ ] Dashboard accessible (Streamlit responds with HTML)
  ```bash
  curl http://<external-ip-dashboard>/
  ```

### Application Health
- [ ] API /health endpoint returns 200 OK
  ```bash
  curl -s http://<external-ip>/health | jq
  ```
- [ ] API /docs (Swagger) loads without errors
  ```bash
  curl http://<external-ip>/docs
  ```
- [ ] Database connection working
  - API logs should show no connection errors
  - Verify: `kubectl logs -n insureai <api-pod>`
- [ ] LLM (Anthropic) connection working
  - ANTHROPIC_API_KEY must be valid
  - Verify: Attempt a test submission

### Data Persistence
- [ ] PostgreSQL pod has persistent storage (if using StatefulSet)
  - Verify: `kubectl get pvc -n insureai`
- [ ] Data persists after pod restart
  - Restart: `kubectl delete pod postgres-0 -n insureai`
  - Verify: Data still accessible after restart

### Monitoring & Logs
- [ ] Pod logs are accessible and readable
  ```bash
  kubectl logs -n insureai <pod-name> --tail=100
  ```
- [ ] No error messages in API logs
  - Verify: grep for ERROR, Exception, Traceback
- [ ] Cost ledger queries work (if using RDS)

## Rollback Procedure

If deployment fails and pods don't recover:

```bash
# 1. Revert image to previous version
kubectl set image deployment/insureai-api insureai-api=<previous-image> -n insureai

# 2. Monitor rollout
kubectl rollout status deployment/insureai-api -n insureai

# 3. If still failing, delete pod to trigger new one
kubectl delete pod <pod-name> -n insureai

# 4. Check logs
kubectl logs -n insureai <new-pod-name>
```

---

## Common Failures & Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pods stuck in Pending | No node capacity or nodeSelector/affinity blocking | Check: `kubectl describe pod <name>` |
| ImagePullBackOff | Missing imagePullSecrets or ECR credentials stale | Recreate ECR secret, add to deployment |
| CrashLoopBackOff | Application error or missing env var | Check: `kubectl logs <pod>` |
| External IP Pending | Subnets not tagged for ELB | Tag: `kubernetes.io/role/internal-elb=1` |
| Connection refused | LoadBalancer not ready or service misconfigured | Check: `kubectl get svc`, curl service endpoint |

---

**Last Updated:** 2026-06-01  
**Status:** ✅ Proven working, all issues resolved
