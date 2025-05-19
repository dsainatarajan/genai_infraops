import os
import time
from collections import defaultdict, deque
import statistics
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import openai

# === Configuration ===
INTERVAL_SECONDS = 60
openai.api_key = os.getenv("OPENAI_API_KEY", "<YOUR_KEY_HERE>")
CPU_THRESHOLD = 0.8  # 80% usage
MEMORY_THRESHOLD = 0.8  # 80% usage
DRY_RUN = True  # Prevent automatic actions if True
ANOMALY_WINDOW = 30  # Data points for anomaly detection
Z_SCORE_THRESHOLD = 3  # Threshold for anomaly detection

# Load cluster config (in-cluster or local kubeconfig)
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
metrics_v1 = client.CustomObjectsApi()

# ML Anomaly Detection storage
historical_metrics = defaultdict(lambda: {
    'cpu': deque(maxlen=ANOMALY_WINDOW),
    'memory': deque(maxlen=ANOMALY_WINDOW)
})

def automate_incident_response(error_msg: str):
    """Take automated actions based on detected issues."""
    if DRY_RUN:
        print(f"Dry run: would take action for: {error_msg}")
        return
    
    try:
        # Handle CrashLoopBackOff pods
        if "CrashLoopBackOff" in error_msg:
            parts = error_msg.split()
            namespace_pod = parts[1].split('/')
            if len(namespace_pod) == 2:
                namespace, pod = namespace_pod[0], namespace_pod[1].rstrip(':')
                v1.delete_namespaced_pod(pod, namespace)
                print(f"Automation: Deleted pod {namespace}/{pod}")

        # Handle Not Ready nodes
        elif "not ready" in error_msg and "Node" in error_msg:
            node_name = error_msg.split()[1]
            body = {"spec": {"unschedulable": True}}
            v1.patch_node(node_name, body)
            print(f"Automation: Cordoned node {node_name}")

        # Handle Deployment scaling
        elif "replicas available" in error_msg and "Deployment" in error_msg:
            parts = error_msg.split()
            dep_info = parts[1].split('/')
            namespace, dep_name = dep_info[0], dep_info[1].rstrip(':')
            deployment = apps_v1.read_namespaced_deployment(dep_name, namespace)
            current_replicas = deployment.spec.replicas or 0
            new_replicas = current_replicas + 1
            patch = {"spec": {"replicas": new_replicas}}
            apps_v1.patch_namespaced_deployment(dep_name, namespace, patch)
            print(f"Automation: Scaled {namespace}/{dep_name} to {new_replicas}")

    except ApiException as e:
        print(f"Automation failed: {e}")
    except Exception as e:
        print(f"Automation error: {e}")

def check_anomalies(name: str, current_cpu: float, current_mem: float):
    """Check for anomalies using statistical methods."""
    # CPU anomaly check
    cpu_values = historical_metrics[name]['cpu']
    if len(cpu_values) >= ANOMALY_WINDOW//2:
        try:
            mean = statistics.mean(cpu_values)
            std = statistics.stdev(cpu_values)
            if std > 0:
                z_score = (current_cpu - mean) / std
                if abs(z_score) > Z_SCORE_THRESHOLD:
                    msg = f"Node {name} CPU anomaly (z={z_score:.2f}, current={current_cpu:.2%})"
                    print_problem(msg)
        except:
            pass

    # Memory anomaly check
    mem_values = historical_metrics[name]['memory']
    if len(mem_values) >= ANOMALY_WINDOW//2:
        try:
            mean = statistics.mean(mem_values)
            std = statistics.stdev(mem_values)
            if std > 0:
                z_score = (current_mem - mean) / std
                if abs(z_score) > Z_SCORE_THRESHOLD:
                    msg = f"Node {name} Memory anomaly (z={z_score:.2f}, current={current_mem:.2%})"
                    print_problem(msg)
        except:
            pass

def check_resource_utilization():
    """Analyze resource usage with anomaly detection."""
    try:
        node_metrics = metrics_v1.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        for item in node_metrics['items']:
            name = item['metadata']['name']
            cpu_usage = parse_resource(item['usage']['cpu'])
            mem_usage = parse_resource(item['usage']['memory'])
            alloc_cpu, alloc_mem = get_node_allocatable(name)
            
            cpu_ratio = cpu_usage / alloc_cpu
            mem_ratio = mem_usage / alloc_mem

            # Threshold checks
            if cpu_ratio > CPU_THRESHOLD or mem_ratio > MEMORY_THRESHOLD:
                err = f"Node {name} high usage - CPU: {cpu_ratio:.2%}, Memory: {mem_ratio:.2%}"
                print_problem(err)

            # Update metrics and check anomalies
            historical_metrics[name]['cpu'].append(cpu_ratio)
            historical_metrics[name]['memory'].append(mem_ratio)
            check_anomalies(name, cpu_ratio, mem_ratio)

    except Exception as e:
        print_problem(f"Failed to fetch metrics: {e}")

def print_problem(error_msg: str):
    print(f"\n❗️ Detected issue: {error_msg}")
    advice = ask_gpt4_for_solution(error_msg)
    print(f"🔍 GPT-4 Analysis:\n{advice}\n{'-'*60}")
    automate_incident_response(error_msg)

# ... (keep existing functions for get_node_allocatable, parse_resource, 
# check_nodes, check_pods, check_deployments, check_services, check_events,
# ask_gpt4_for_solution, and monitor_loop unchanged)