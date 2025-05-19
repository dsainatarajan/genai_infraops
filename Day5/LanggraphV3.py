import os
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import openai

# === Configuration ===
INTERVAL_SECONDS = 60
openai.api_key = os.getenv("OPENAI_API_KEY", "<YOUR_KEY_HERE>")

# Load cluster config (in‑cluster or local kubeconfig)
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


def ask_gpt4_for_solution(error_info: str) -> str:
    """Send the error info to GPT‑4 and return its advice."""
    prompt = (
        "I have the following Kubernetes cluster issue:\n"
        f"{error_info}\n\n"
        "Please explain the likely root cause and suggest concrete remediation steps."
    )
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a Kubernetes SRE expert."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


def check_nodes() -> None:
    """Verify all nodes are Ready."""
    ret = v1.list_node()
    for node in ret.items:
        for cond in node.status.conditions:
            if cond.type == "Ready" and cond.status != "True":
                err = f"Node {node.metadata.name} not ready: {cond.reason} ({cond.message})"
                print_problem(err)


def check_pods() -> None:
    """Look for pods not in Running/Succeeded."""
    ret = v1.list_pod_for_all_namespaces()
    for pod in ret.items:
        phase = pod.status.phase
        if phase not in ("Running", "Succeeded"):
            err = (
                f"Pod {pod.metadata.namespace}/{pod.metadata.name} in phase {phase}. "
                f"Reason: {pod.status.reason or 'unknown'}"
            )
            print_problem(err)


def check_deployments() -> None:
    """Ensure each Deployment’s available replicas == desired replicas."""
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


def check_services() -> None:
    """Verify each Service has Endpoints backing it."""
    svcs = v1.list_service_for_all_namespaces().items
    for svc in svcs:
        eps = v1.read_namespaced_endpoints(svc.metadata.name, svc.metadata.namespace)
        subsets = eps.subsets or []
        if not subsets or all(len(s.addresses or []) == 0 for s in subsets):
            err = f"Service {svc.metadata.namespace}/{svc.metadata.name} has no endpoints"
            print_problem(err)


def check_events() -> None:
    """Scan for recent Warning events."""
    now = int(time.time())
    evs = v1.list_event_for_all_namespaces().items
    for ev in evs:
        # only look at events in the last INTERVAL_SECONDS
        if (now - ev.last_timestamp.timestamp()) < INTERVAL_SECONDS and ev.type == "Warning":
            err = (
                f"Event in {ev.metadata.namespace}: {ev.involved_object.kind}/"
                f"{ev.involved_object.name}: {ev.message}"
            )
            print_problem(err)


def print_problem(error_msg: str) -> None:
    """Print the error and call GPT‑4 for analysis."""
    print(f"\n❗️ Detected problem: {error_msg}")
    advice = ask_gpt4_for_solution(error_msg)
    print(f"🔍 GPT‑4 suggests:\n{advice}\n{'-'*60}")


def monitor_loop():
    print("Starting Kubernetes health monitor (CTRL+C to exit)...")
    while True:
        try:
            check_nodes()
            check_pods()
            check_deployments()
            check_services()
            check_events()
        except ApiException as e:
            print_problem(f"Kubernetes API exception: {e}")
        except Exception as e:
            print_problem(f"Unexpected error in monitor: {e}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    monitor_loop()
