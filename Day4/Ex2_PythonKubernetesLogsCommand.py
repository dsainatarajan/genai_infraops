#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extended Kubernetes Python Client Example Script
Provides multiple utilities to interact with Kubernetes clusters,
showing off capabilities like listing, creating, updating, scaling,
watching events, fetching logs, executing commands, and managing
ConfigMaps and Secrets.
"""
import argparse
import sys
import time
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
# Load kubeconfig (~/.kube/config) or in-cluster config
try:
    config.load_kube_config()
except Exception:
    config.load_incluster_config()

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()


def list_pods(namespace=None):
    """List all pods, optionally in a specific namespace."""
    print(f"Listing pods in namespace: {namespace or 'all'}")
    pods = core_v1.list_pod_for_all_namespaces() if not namespace else core_v1.list_namespaced_pod(namespace)
    for pod in pods.items:
        print(f"{pod.status.pod_ip}\t{pod.metadata.namespace}\t{pod.metadata.name}")


def list_services(namespace=None):
    """List services in a namespace or across all namespaces."""
    print(f"Listing services in namespace: {namespace or 'all'}")
    svcs = core_v1.list_service_for_all_namespaces() if not namespace else core_v1.list_namespaced_service(namespace)
    for svc in svcs.items:
        print(f"{svc.metadata.namespace}\t{svc.metadata.name}\t{svc.spec.type}\t{svc.spec.cluster_ip}")


def create_namespace(name):
    """Create a new namespace."""
    ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
    try:
        core_v1.create_namespace(ns_body)
        print(f"Namespace '{name}' created.")
    except ApiException as e:
        print(f"Failed to create namespace: {e}")


def delete_namespace(name):
    """Delete a namespace."""
    try:
        core_v1.delete_namespace(name)
        print(f"Namespace '{name}' deletion initiated.")
    except ApiException as e:
        print(f"Failed to delete namespace: {e}")


def create_deployment(name, image, replicas, namespace='default'):
    """Create a Deployment in the specified namespace."""
    container = client.V1Container(
        name=name,
        image=image,
        ports=[client.V1ContainerPort(container_port=80)]
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={'app': name}),
        spec=client.V1PodSpec(containers=[container])
    )
    spec = client.V1DeploymentSpec(
        replicas=replicas,
        template=template,
        selector={'matchLabels': {'app': name}}
    )
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name),
        spec=spec
    )
    try:
        apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
        print(f"Deployment '{name}' created in namespace '{namespace}'.")
    except ApiException as e:
        print(f"Failed to create deployment: {e}")


def scale_deployment(name, replicas, namespace='default'):
    """Scale an existing Deployment."""
    body = {'spec': {'replicas': replicas}}
    try:
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        print(f"Deployment '{name}' scaled to {replicas} replicas.")
    except ApiException as e:
        print(f"Failed to scale deployment: {e}")


def create_service(name, port, target_port, namespace='default'):
    """Create a ClusterIP Service for a Deployment."""
    svc_body = client.V1Service(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1ServiceSpec(
            selector={'app': name},
            ports=[client.V1ServicePort(port=port, target_port=target_port)]
        )
    )
    try:
        core_v1.create_namespaced_service(namespace=namespace, body=svc_body)
        print(f"Service '{name}' created on port {port} -> target {target_port} in '{namespace}'.")
    except ApiException as e:
        print(f"Failed to create service: {e}")


def watch_events(namespace=None, timeout=60):
    """Watch events in cluster or namespace for a duration."""
    w = watch.Watch()
    counter = 0
    print(f"Watching events in namespace: {namespace or 'all'}")
    try:
        stream = w.stream(core_v1.list_event_for_all_namespaces if not namespace else core_v1.list_namespaced_event,
                          namespace=namespace, timeout_seconds=timeout)
        for event in stream:
            obj = event['object']
            print(f"{event['type']} - {obj.metadata.namespace}/{obj.involved_object.kind}: {obj.message}")
            counter += 1
            if counter >= 10:
                w.stop()
    except ApiException as e:
        print(f"Watch failed: {e}")


def get_pod_logs(name, namespace='default', tail_lines=100):
    """Fetch logs from a Pod."""
    try:
        logs = core_v1.read_namespaced_pod_log(name=name, namespace=namespace, tail_lines=tail_lines)
        print(f"Logs from {name} (last {tail_lines} lines):\n{logs}")
    except ApiException as e:
        print(f"Failed to fetch logs: {e}")


def exec_command_in_pod(name, namespace='default', command=['/bin/sh', '-c', 'ls']):
    """Execute a command in a Pod and return the output."""
    try:
        resp = stream(core_v1.connect_get_namespaced_pod_exec,
                      name, namespace,
                      command=command,
                      stderr=True, stdin=False,
                      stdout=True, tty=False)
        print(f"Command output:\n{resp}")
    except ApiException as e:
        print(f"Exec failed: {e}")

pod_name = "REPLACE_POD_NAME_HERE"
exec_command_in_pod(pod_name, command=['/bin/sh', '-c', 'mkdir /hello'])


get_pod_logs(pod_name)



