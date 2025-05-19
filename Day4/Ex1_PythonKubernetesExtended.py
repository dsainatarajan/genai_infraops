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

list_pods()
list_services('default')
create_namespace("amdocsdemo1")
create_deployment("httpdemo2", "httpd", 3)
time.sleep(30)
list_pods()
scale_deployment("httpdemo2", 5)
list_pods()


