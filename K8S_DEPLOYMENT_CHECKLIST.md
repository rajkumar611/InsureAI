# K8s Deployment Checklist — InsureAI on AWS EKS

## Status: Ready for CloudShell Deployment

All K8s manifests have been created locally:
- ✓ k8s/namespace.yaml
- ✓ k8s/configmap.yaml
- ✓ k8s/secret.yaml.example (template)
- ✓ k8s/postgres-statefulset.yaml
- ✓ k8s/api-deployment.yaml
- ✓ k8s/streamlit-deployment.yaml
- ✓ Docker image built and pushed to ECR

---

## Next Steps (In CloudShell)

### 1. Connect kubectl to EKS Cluster

```bash
aws eks update-kubeconfig --name insureai-eks --region ap-southeast-2
```

Verify connection:
```bash
kubectl get nodes
```

Expected output: 2 nodes in Ready state

### 2. Create Secret from Template

Copy template and add real values:
```bash
# In CloudShell, create the secret file with actual values
cat > secret.yaml << 'SECRETEOF'
apiVersion: v1
kind: Secret
metadata:
  name: insureai-secrets
  namespace: insureai
type: Opaque
stringData:
  POSTGRES_PASSWORD: "your-secure-postgres-password"
  ANTHROPIC_API_KEY: "sk-ant-your-real-api-key"
  DATABASE_URL: "postgresql+asyncpg://dbinsureai:your-secure-postgres-password@postgres.insureai.svc.cluster.local:5432/aus_underwriting"
SECRETEOF
```

### 3. Apply K8s Manifests in Order

**DO NOT COMMIT secret.yaml to git** — it contains real secrets.

```bash
# Apply in this order:
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f secret.yaml              # Use the one you just created above
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/streamlit-deployment.yaml
```

### 4. Verify Deployment

```bash
# Watch pods start
kubectl get pods -n insureai -w

# When all are Running, check services
kubectl get svc -n insureai
```

Expected output:
```
NAME               TYPE           CLUSTER-IP       EXTERNAL-IP
insureai-api       LoadBalancer   10.x.x.x         <pending or IP>
insureai-dashboard LoadBalancer   10.x.x.x         <pending or IP>
postgres           ClusterIP      None             <none>
```

### 5. Wait for External IPs

AWS takes 1-2 minutes to assign external IPs to LoadBalancer services:

```bash
# Keep checking until both have external IPs
kubectl get svc -n insureai -w
```

Once assigned, you'll have:
- API: `http://<API-EXTERNAL-IP>`
- Dashboard: `http://<DASHBOARD-EXTERNAL-IP>`

### 6. Test Services

```bash
# Test API health
curl http://<API-EXTERNAL-IP>/health

# Test API is ready
curl http://<API-EXTERNAL-IP>/health/ready

# Test Swagger docs
curl http://<API-EXTERNAL-IP>/docs
```

### 7. Access Dashboard in Browser

Open in your browser:
```
http://<DASHBOARD-EXTERNAL-IP>
```

You should see the Streamlit underwriter portal.

---

## Troubleshooting

### Pods stuck in Pending
```bash
# Check why pod can't be scheduled
kubectl describe pod <pod-name> -n insureai
```

### Pods not ready / CrashLoopBackOff
```bash
# Check pod logs
kubectl logs <pod-name> -n insureai

# For init container errors
kubectl logs <pod-name> -n insureai -c migrate
```

### Database connection errors
```bash
# Verify postgres pod is running
kubectl get pod postgres-0 -n insureai

# Check postgres logs
kubectl logs postgres-0 -n insureai

# Verify secret was created
kubectl get secret insureai-secrets -n insureai -o yaml
```

### Services have no external IP
```bash
# Check if LoadBalancer is working
kubectl describe svc insureai-api -n insureai

# AWS takes time — wait 2-3 minutes
# If still pending after 5 min, check AWS console for issues
```

---

## GitHub Actions Integration

Once everything works locally, update GitHub Actions secrets:

1. Go to GitHub repo → Settings → Secrets and variables → Actions
2. Add/verify these secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `EKS_CLUSTER_NAME` = `insureai-eks`
   - `AWS_REGION` = `ap-southeast-2`

3. Push a commit to main:
```bash
git add -A
git commit -m "Add K8s manifests for EKS deployment"
git push origin main
```

GitHub Actions will automatically build, push to ECR, and deploy to EKS.

---

## Final Verification Checklist

- [ ] `kubectl get pods -n insureai` shows all pods in Running state
- [ ] `kubectl get svc -n insureai` shows API and Dashboard with external IPs
- [ ] `curl http://<API-IP>/health` returns `{"status": "OK"}`
- [ ] `curl http://<API-IP>/docs` returns Swagger UI
- [ ] `http://<DASHBOARD-IP>` loads Streamlit portal in browser
- [ ] Can submit a document via the portal or API
- [ ] Cost dashboard shows the API calls
- [ ] GitHub Actions deploys successfully on next push to main

---

**Next:** Follow the steps above in AWS CloudShell to deploy to EKS.
