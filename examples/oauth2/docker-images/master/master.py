import argparse
import socket
import os
import tarfile
import time
import sys

from kubernetes import client, config
from kubernetes.client import V1Container
from kubernetes.client import V1EnvVar
from kubernetes.client import V1EnvVarSource
from kubernetes.client import V1SecretKeySelector
from kubernetes.client import V1Job
from kubernetes.client import V1JobSpec
from kubernetes.client import V1ObjectMeta
from kubernetes.client import V1PodSpec
from kubernetes.client import V1PodTemplateSpec
from kubernetes.client import V1DeleteOptions
from kubernetes.client import V1Secret
from kubernetes.client import V1ResourceRequirements

from minio import Minio
from minio.error import (ResponseError, BucketAlreadyOwnedByYou,
                         BucketAlreadyExists)

def main(s3_endpoint, bucket, object_key, parallelism, namespace, env_secret_name):
    bucket = bucket or os.environ['BUCKET']
    object_key = object_key or os.environ['OBJECT_KEY']

    archive_name = 'pkg.tar.gz'

    # Initialize minioClient with an endpoint and access/secret keys.
    s3 = Minio(s3_endpoint,
               access_key=os.environ['ACCESS_KEY'],
               secret_key=os.environ['SECRET_KEY'],
               secure=False)

    # Get a full object and prints the original object stat information.
    try:
        print(s3.fget_object(bucket, object_key, archive_name))
    except ResponseError as err:
        print(err)

    tar = tarfile.open(archive_name)
    tar.extractall()
    tar.close()

    # Configs can be set in Configuration class directly or using helper utility
    # config.load_kube_config()
    config.load_incluster_config()

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

    secret_name = "kubedt-pytest"

    memory_size = '64Mi'
    memory_usage = {"memory": memory_size}

    access_key_env = V1EnvVar(name="ACCESS_KEY",
                              value_from=V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name=secret_name, key="accesskey", )))
    secret_key_env = V1EnvVar(name="SECRET_KEY",
                              value_from=V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name=secret_name, key="secretkey", )))

    envs = [access_key_env, secret_key_env]

    env_secret = v1.read_namespaced_secret(name=env_secret_name, namespace=namespace)
    for k in env_secret.data.keys():
        env = V1EnvVar(name=k, value_from=V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name=env_secret_name, key=k)))
        envs.append(env)

    worker_port = 8888
    args = [
        ":%d" % worker_port
    ]
    job_name = 'kubedt-pytest-worker'

    resp = batchv1.list_job_for_all_namespaces(field_selector="metadata.name=%s" % job_name)
    if len(resp.items) == 0:
        pod_template_spec = V1PodTemplateSpec(
            metadata=V1ObjectMeta(name=job_name, labels={"app": job_name}),
            spec=V1PodSpec(restart_policy="Never", containers=[
                V1Container(args=args,
                            image="mumoshu/%s" % job_name, image_pull_policy='IfNotPresent',
                            name=job_name, env=envs,
                            # it fails like "oci runtime error: write /proc/26452/oom_score_adj: invalid argument" without resource req
                            resources=V1ResourceRequirements(limits=memory_usage, requests=memory_usage), )]))
        job = V1Job(
            api_version="batch/v1", kind='Job',
            metadata=V1ObjectMeta(
                name=job_name,
            ),
            spec=V1JobSpec(
                completions=parallelism,
                parallelism=parallelism,
                template=pod_template_spec
            )
        )
        resp = batchv1.create_namespaced_job(
            namespace=namespace,
            body=job
        )

        print("Job %s created. status='%s'" % (job_name, str(resp.status)))
    else:
        print("Job %s exists." % job_name)

    trials = 0
    max_trials = 10
    pods = None

    while True:
        if trials >= max_trials:
            print("Timed out while waiting for %s to be ready" % job_name)
            sys.exit(1)
        trials += 1
        print("Listing worker pods: Trial #%d" % trials)
        resp = v1.list_namespaced_pod(namespace=namespace, label_selector="job-name=%s" % job_name)
        num_pods = len(resp.items)
        print("Fetched %d pods" % num_pods)
        pods = resp.items
        print("%s statuses: %s" % (job_name, ", ".join([pod.status.phase for pod in pods])))
        par_in_int = int(parallelism)
        print("num pods = %d, parallelism = %d" % (num_pods, par_in_int), (type(num_pods), type(par_in_int)))
        all_exist = (num_pods >= par_in_int)
        num_running = 0
        for pod in resp.items:
            if pod.status.phase == 'Running':
                num_running += 1
        all_running = num_running >= parallelism
        print({'all_exist': all_exist, 'num_running': num_running, 'num_pods': num_pods, 'par_in_int': par_in_int, 'all_running': all_running})
        if all_exist and all_running:
            break
        time.sleep(5)

    os.system('ls .')

    addrs = [pod.status.pod_ip for pod in pods if pod.status.phase == 'Running']

    print({'num_addrs': len(addrs)})

    # addrs = [str(i[4][0]) for i in socket.getaddrinfo(job_name, worker_port)]
    txs = ["--tx socket=%s:8888" % a for a in addrs]
    cmd = "pipenv run py.test -d %s --rsyncdir ." % (" ".join(txs))

    tries = 100

    status = None

    for n in range(tries):
        status = os.WEXITSTATUS(os.system(cmd))
        if status == 3:
            time.sleep(5)
            continue
        break

    resp = batchv1.delete_namespaced_job(name=job_name, namespace=namespace, body=V1DeleteOptions())

    print("Job %s deleted. status='%s'" % (job_name, str(resp.status)))

    print("Command `%s` failed with exit status %d" % (cmd, status))

    sys.exit(status)


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
        "--parallelism",
        type=int,
        default=1,
        help="Number of workers to distributed subsets of tests for parallel execution"
    )
    parser.add_argument(
        "--env-secret-name",
        type=str,
        default="",
        help="Name of k8s secret containing env vars passed to remote processes running tests"
    )
    parsed = parser.parse_args()
    # https://stackoverflow.com/questions/33712615/using-argparse-with-function-that-takes-kwargs-argument
    opts = vars(parsed)
    main(**opts)
