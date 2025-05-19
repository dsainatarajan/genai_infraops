import os
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import openai
from openai import OpenAI
# === Configuration ===
INTERVAL_SECONDS = 120
openai.api_key = os.getenv("OPENAI_API_KEY", "<YOUR_KEY_HERE>")
CPU_THRESHOLD = 0.25  # Increase to 0.8 to check for 80% usage
MEMORY_THRESHOLD = 0.25  # Increase to 0.8 to check for 80% usage
openaiclient = OpenAI()
# Load cluster config (in-cluster or local kubeconfig)
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
metrics_v1 = client.CustomObjectsApi()
openaiclient = OpenAI()

def ask_gpt4_for_solution(error_info: str) -> str:
    prompt = (
        "The following issue was observed in a Kubernetes cluster:\n"
        f"{error_info}\n\n"
        "Provide the likely root cause, remediation steps, and potential optimizations."
    )
    resp = openaiclient.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a Kubernetes SRE and capacity planning expert."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


def check_resource_utilization():
    """Analyze resource usage and suggest capacity planning improvements."""
    try:
        node_metrics = metrics_v1.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        for item in node_metrics['items']:
            name = item['metadata']['name']
            cpu_usage = parse_resource(item['usage']['cpu'])
            mem_usage = parse_resource(item['usage']['memory'])
            alloc_cpu, alloc_mem = get_node_allocatable(name)
            cpu_ratio = cpu_usage / alloc_cpu
            mem_ratio = mem_usage / alloc_mem

            if cpu_ratio > CPU_THRESHOLD or mem_ratio > MEMORY_THRESHOLD:
                err = (
                    f"Node {name} high usage - CPU: {cpu_ratio:.2%}, Memory: {mem_ratio:.2%}"
                )
                print_problem(err)
    except Exception as e:
        print_problem(f"Failed to fetch metrics: {e}")


def get_node_allocatable(node_name):
    """Get allocatable CPU and memory for a node."""
    node = v1.read_node(node_name)
    cpu = parse_resource(node.status.allocatable['cpu'])
    memory = parse_resource(node.status.allocatable['memory'])
    return cpu, memory


def parse_resource(val):
    """Convert CPU and memory to float values."""
    if val.endswith('n'):
        return float(val[:-1]) / 1e9
    if val.endswith('m'):
        return float(val[:-1]) / 1000
    if val.endswith('Ki'):
        return float(val[:-2]) * 1024
    if val.endswith('Mi'):
        return float(val[:-2]) * 1024 ** 2
    if val.endswith('Gi'):
        return float(val[:-2]) * 1024 ** 3
    if val.endswith('Ti'):
        return float(val[:-2]) * 1024 ** 4
    try:
        return float(val)
    except:
        return 0.0


def check_nodes():
    ret = v1.list_node()
    for node in ret.items:
        for cond in node.status.conditions:
            if cond.type == "Ready" and cond.status != "True":
                err = f"Node {node.metadata.name} not ready: {cond.reason} ({cond.message})"
                print_problem(err)


def check_pods():
    ret = v1.list_pod_for_all_namespaces()
    for pod in ret.items:
        phase = pod.status.phase
        if phase not in ("Running", "Succeeded"):
            err = (
                f"Pod {pod.metadata.namespace}/{pod.metadata.name} in phase {phase}. "
                f"Reason: {pod.status.reason or 'unknown'}"
            )
            print_problem(err)


def check_deployments():
    ret = apps_v1.list_deployment_for_all_namespaces()
    for dep in ret.items:
        desired = dep.spec.replicas or 0
        avail = dep.status.available_replicas or 0
        if avail < desired:
            err = (
                f"Deployment {dep.metadata.namespace}/{dep.metadata.name}: "
                f"{avail}/{desired} replicas available"
            )
            print_problem(err)


def check_services():
    svcs = v1.list_service_for_all_namespaces().items
    for svc in svcs:
        eps = v1.read_namespaced_endpoints(svc.metadata.name, svc.metadata.namespace)
        subsets = eps.subsets or []
        if not subsets or all(len(s.addresses or []) == 0 for s in subsets):
            err = f"Service {svc.metadata.namespace}/{svc.metadata.name} has no endpoints"
            print_problem(err)


def check_events():
    now = int(time.time())
    evs = v1.list_event_for_all_namespaces().items
    for ev in evs:
        if (now - ev.last_timestamp.timestamp()) < INTERVAL_SECONDS and ev.type == "Warning":
            err = (
                f"Event in {ev.metadata.namespace}: {ev.involved_object.kind}/"
                f"{ev.involved_object.name}: {ev.message}"
            )
            print_problem(err)


def print_problem(error_msg: str):
    print(f"\n❗️ Detected issue: {error_msg}")
    advice = ask_gpt4_for_solution(error_msg)
    print(f"🔍 GPT-4 Analysis:\n{advice}\n{'-'*120}")


def monitor_loop():
    print("🚀 Starting AI-driven Capacity Planning and Optimization Monitor (CTRL+C to exit)...")
    while True:
        try:
            check_nodes()
            check_pods()
            check_deployments()
            check_services()
            check_events()
            check_resource_utilization()
        except ApiException as e:
            print_problem(f"Kubernetes API exception: {e}")
        except Exception as e:
            print_problem(f"Unexpected error in monitor: {e}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    monitor_loop()

