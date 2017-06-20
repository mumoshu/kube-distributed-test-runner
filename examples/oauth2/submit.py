import argparse
import socket
import os
import tarfile
import time
import sys
import logging
import thread
import threading

from kubernetes import client, config
from kubernetes.client import V1Container
from kubernetes.client import V1EnvVar
from kubernetes.client import V1EnvVarSource
from kubernetes.client import V1SecretKeySelector
from kubernetes.client import V1Job
from kubernetes.client import V1Pod
from kubernetes.client import V1JobSpec
from kubernetes.client import V1ObjectMeta
from kubernetes.client import V1PodSpec
from kubernetes.client import V1PodTemplateSpec
from kubernetes.client import V1Secret
from kubernetes.client import V1ResourceRequirements

from minio import Minio
from minio.error import (ResponseError, BucketAlreadyOwnedByYou,
                         BucketAlreadyExists)

import tarfile


def make_tarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.sep)


def main(s3_endpoint, bucket, object_key, access_key, secret_key, parallelism, namespace, verbose, inherit_envs):
    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        import httplib as http_client

    # You must initialize logging, otherwise you'll not see debug output.
    if verbose:
        http_client.HTTPConnection.debuglevel = 1
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("client")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    bucket = bucket or os.environ['BUCKET']
    object_key = object_key or os.environ['OBJECT_KEY']
    access_key = access_key or os.environ['ACCESS_KEY']
    secret_key = secret_key or os.environ['SECRET_KEY']
    parallelism = parallelism or os.environ['PARALLELISM']
    namespace = namespace or os.environ.get('NAMESPACE', 'default')
    s3_endpoint = s3_endpoint or os.environ.get('S3_ENDPOINT', 'minio-minio-svc:9000')

    archive_name = "pkg.tar.gz"
    make_tarfile(archive_name, ".")

    # Initialize s3 with an endpoint and access/secret keys.
    s3 = Minio(
        endpoint=s3_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=False
    )

    if not s3.bucket_exists(bucket_name=bucket):
        print(s3.make_bucket(bucket_name=bucket))

    # Get a full object and prints the original object stat information.
    try:
        print(s3.fput_object(bucket, object_key, archive_name))
    except ResponseError as err:
        print(err)

    # Configs can be set in Configuration class directly or using helper utility
    config.load_kube_config()

    v1 = client.CoreV1Api()

    print("Listing pods with their IPs:")
    ret = v1.list_pod_for_all_namespaces(watch=False)
    for i in ret.items:
        print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    batchv1 = client.BatchV1Api()

    # resp = batchv1.create_namespaced_job(namespace=namespace, body="""
    # apiVersion: batch/v1
    # kind: Job
    # metadata:
    #   name: kubedt-pytest-master
    # spec:
    #   template:
    #     metadata:
    #       name: kubedt-pytest-master
    #     spec:
    #       containers:
    #       - name: kubedt-pytest-master
    #         image: mumoshu/kubedt-pytest-master
    #       restartPolicy: Never
    # """)

    # Missing base64 encode results in the weird oom_score_adj error
    # https://github.com/kubernetes/kubernetes/issues/30861
    secret_name = "kubedt-pytest"
    secret = V1Secret(metadata=V1ObjectMeta(
        name=secret_name
    ), data={
        "accesskey": access_key.encode('base64'),
        "secretkey": secret_key.encode('base64'),
    })
    resp = v1.create_namespaced_secret(namespace=namespace, body=secret)

    env_secret_data = {}
    for e in inherit_envs:
        env_secret_data[e] = os.environ[e].encode('base64')
    env_secret_name = "kubedt-pytest-env"
    env_secret = V1Secret(metadata=V1ObjectMeta(
        name=env_secret_name
    ), data=env_secret_data)
    resp = v1.create_namespaced_secret(namespace=namespace, body=env_secret)

    print(resp)

    memory_size = '64Mi'
    memory_usage = {"memory": memory_size}

    access_key_env = V1EnvVar(name="ACCESS_KEY",
                   value_from=V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name=secret_name, key="accesskey", )))
    secret_key_env = V1EnvVar(name="SECRET_KEY",
                   value_from=V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name=secret_name, key="secretkey", )))
    args = [
        "--bucket", bucket,
        "--object-key", object_key,
        "--parallelism", str(parallelism),
        "--s3-endpoint", s3_endpoint,
        "--namespace", namespace,
        "--env-secret-name", env_secret_name,
    ]
    pod_meta = V1ObjectMeta(name="kubedt-pytest-master", labels={"app": "kubedt-pytest-master"})
    pod_spec = V1PodSpec(restart_policy="Never", containers=[
        V1Container(args=args,
                    image="mumoshu/kubedt-pytest-master", image_pull_policy='IfNotPresent',
                    name="kubedt-pytest-master", env=[access_key_env,
                                                      secret_key_env],
                    # it fails like "oci runtime error: write /proc/26452/oom_score_adj: invalid argument" without resource req
                    resources=V1ResourceRequirements(limits=memory_usage, requests=memory_usage), )])
    pod = V1Pod(
        api_version="v1",
        kind='Pod',
        metadata=pod_meta,
        spec=pod_spec
    )
    resp = v1.create_namespaced_pod(
        namespace=namespace,
        body=pod
    )

    print("Pod created. status='%s'" % str(resp.status))
    print(resp)

    print("Waiting for %s to start" % pod.metadata.name)
    max_trials = 10
    trials = 0
    while True:
        if trials >= max_trials:
            print("Timed out while waiting for kubedt-pytest-master to be running")
            sys.exit(1)
        trials += 1
        resp = v1.list_namespaced_pod(namespace=namespace, field_selector="metadata.name=%s" % pod.metadata.name)
        print("Fetched %d pods" % len(resp.items))
        print("Status: %s" % ", ".join([pod.status.phase for pod in resp.items]))
        if len(resp.items) > 0:
            pod = resp.items[0]
            if pod.status.phase != 'Pending':
                break
            print('Status is %s' % pod.status.phase)
        time.sleep(5)

    print("Tailing logs")
    stopped = threading.Event()
    def tail(pod, namespace):
        print("Requesting logs")
        # See the issue below for how log-following works in client-python
        # https://github.com/kubernetes-incubator/client-python/issues/199
        r = v1.read_namespaced_pod_log(name=pod.metadata.name, namespace=namespace, follow=True, _preload_content=False)

        print("Started following logs")
        # See the doc below for how streaming works in urllib3
        # https://github.com/shazow/urllib3/blob/master/docs/advanced-usage.rst#streaming-and-io
        # for chunk in r.stream(32):
        for chunk in r:
            if stopped.is_set():
                break
            sys.stdout.write(chunk)
            sys.stdout.flush()

        print("Stopped following")

        r.release_conn
    thread.start_new_thread(tail, (), {'pod': pod, 'namespace': namespace})

    trials = 0
    max_trials = 10

    time.sleep(5)

    print("Waiting for the pod to stop")
    while pod.status.phase not in ['Failed', 'Completed']:
        if trials >= max_trials:
            print("Timed out while waiting for kubedt-pytest-master to stop")
            sys.exit(1)
        trials += 1
        resp = v1.list_namespaced_pod(namespace=namespace, field_selector="metadata.name=%s" % pod.metadata.name)
        print("Fetched %d pods" % len(resp.items))
        print("Status: %s" % ", ".join([pod.status.phase for pod in resp.items]))
        if len(resp.items) > 0:
            pod = resp.items[0]
        time.sleep(5)

    print("%s is in %s" % (pod.metadata.name, pod.status.phase))

    if not stopped.is_set():
        print("Stopping log following...")
        stopped.set()

    if pod.status.phase == 'Failed':
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.register("type", "bool", lambda v: v.lower() == "true")
    parser.add_argument(
        "--s3-endpoint",
        type=str,
        default="",
        help="hostport of s3/minio endpoint for persisting archived test artifacts for distribution"
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default="",
        help="Name of s3/minio bucket to persist archived test artifacts for distribution"
    )
    parser.add_argument(
        "--object-key",
        type=str,
        default="",
        help="Name of s3/minio object to persist archived test artifacts for distribution"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="default",
        help="Name of k8s namespace to create and run a kubedt-pytest-master/worker"
    )
    parser.add_argument(
        "--access-key",
        type=str,
        default="default",
        help="Access key for s3/minio"
    )
    parser.add_argument(
        "--secret-key",
        type=str,
        default="default",
        help="Secret key for s3/minio"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="Number of workers to distributed subsets of tests for parallel execution"
    )
    parser.add_argument(
        "--verbose",
        type=bool,
        default=False,
        help="Set to true for verbose logging"
    )
    parser.add_argument(
        "--inherit-envs",
        type=str,
        nargs='*',
        help="Names of env vars inherited from here to the remote process running tests"
    )
    parsed = parser.parse_args()
    # https://stackoverflow.com/questions/33712615/using-argparse-with-function-that-takes-kwargs-argument
    opts = vars(parsed)
    main(**opts)
