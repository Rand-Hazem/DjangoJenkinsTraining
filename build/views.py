from django.shortcuts import render
from rest_framework import generics
from .serializers import BuildSerializer
from .models import Build
from .appconfig import Config
from datetime import date
from django.db.models import Max, Avg
from django.views import View
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from rest_framework.pagination import PageNumberPagination
import json
import requests

"""
read data from jenkinz and store in db  ...............................................................
"""


def run_test_job_build(url):
    req = requests.get(url, auth=(Config.jenkins_user['username'], Config.jenkins_user['password']))
    if req.status_code == 200:
        return req.json()
    return None


def analyze_action(actions, build_obj):
    count = 0
    for node in actions:
        if not node:
            continue
        print(node['_class'])
        if node['_class'] == 'hudson.model.ParametersAction' or node[
            '_class'] == 'com.tikal.jenkins.plugins.multijob.MultiJobParametersAction':
            build_obj.param = {x['name']: x['value'] for x in node['parameters']}
            # print("param "+ node['_class'])
            # print(build_obj.param)
            # print()
            count += 1
        elif node['_class'] == 'hudson.model.CauseAction':
            # build_obj.cause = node['shortDescription']
            # print("cauees " + node['_class'])
            # print(build_obj.cause)
            print(node)
            count += 1
        if count == 2:
            break


def read_build(b):
    build = Build()
    analyze_action(b.get('actions'), build)
    build.num = b.get('id')
    build.description = b.get('description')
    build.duration = b.get('duration')
    build.result = b.get('result') == 'SUCCESS'
    build.url = b.get('url')
    build.date = date.fromtimestamp(b.get('timestamp') / 1000)
    build.save()

    if b.get('subBuilds'):
        for sub in b.get('subBuilds'):
            data = run_test_job_build('http://35.157.133.88:8080/' + sub['url'] + '/api/json')
            if data:
                sub_build = read_build(data)
                sub_build.is_sub = True
                sub_build.save()
                build.sub_builds.add(sub_build)
        build.save()
    return build


def save_builds():
    data = run_test_job_build(Config.jobs['run_test']['url'])
    if not data:
        return
    max = Build.objects.filter(is_sub__exact=False).aggregate(Max('num'))['num__max']
    max = max if max else 0
    for b in data['builds']:
        if int(b['id']) > max:
            read_build(b)


"""
 ...............................................................
"""


class BuildsListPagination(PageNumberPagination):
    page_size = 4


class BuildsListAPIView(generics.ListAPIView):
    serializer_class = BuildSerializer
    pagination_class = BuildsListPagination

    def get_queryset(self):
        save_builds()
        return Build.objects.filter(is_sub__exact=False).order_by('num').reverse()


class Dashboard(View):
    @staticmethod
    def get(request):
        return render(request, "dashboard.html", {})


class Trigger(View):
    @staticmethod
    def get(request):
        return render(request, 'trigger.html', {})

    @staticmethod
    def post(request):
        url = Config.jobs['run_test']['trigger']['url']. \
            format(min=request.POST['min'], max=request.POST['max'], threshold=request.POST['th'])
        req = requests.post(url, auth=(Config.jenkins_user['username'], Config.jenkins_user['token']))
        if req.status_code == 201:
            return HttpResponse(status=201)
        return HttpResponseForbidden()


def buildsRate(requests):
    response_data = {'rates': list(Build.objects.filter(is_sub__exact=False)
                                   .extra(select={'name': 'date'}).values('name').annotate(y=Avg('result')))}
    return JsonResponse(response_data)
