import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dependencies"))

import sp
import json
from swagger_parser import SwaggerParser
import requests
import concurrent.futures

class OpenAPIModule(sp.BaseModule):

	pluginInfo = {
		"name" : "OpenAPI Plugin",
		"description" : "Parse swagger files and create Actions",
		"author" : "SP",
		"version" : (1, 0),
		"spVersion" : (1, 2, 0),
		"helpPath" : os.path.join(os.path.dirname(os.path.abspath(__file__)),"help.md")
	}

	def __init__(self):
		self.threadPool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
		sp.BaseModule.__init__(self)
		
	def afterInit(self):

		self.host = self.moduleContainer.addStringParameter("Host", "")
		self.basePath = self.moduleContainer.addStringParameter("Base Path", "")
		self.swaggerFile = self.moduleContainer.addFileParameter("Swagger File", "swagger.json")
		self.parse = self.moduleContainer.addTrigger("Parse")
		
	def onParameterFeedback(self, parameter):
		if parameter == self.swaggerFile or parameter == self.parse:
			self.parseSwaggerFile(self.swaggerFile.value)

	def getUrl(self, endpoint):
		return self.host.value + self.basePath.value + endpoint
	
	def request(self, method, endpoint, *args):
		try:
			url = self.getUrl(endpoint)
			print(f"Sending request: {method} {args}")

			spec = self.spec['paths'][endpoint][method]
			jsonData = None
			formBodyData = None
			query = ""
			headers = {'Content-Type': "application/json", 'Accept': "application/json"}
			i = 0
			for p in spec.get("parameters", []):
				paramValue = args[i]
				if p["in"] == "path":
					url = url.replace("{"+p["name"]+"}", str(paramValue))
				elif p["in"] == "body":
					try:
						jsonData = json.loads(paramValue)
					except Exception as e:
						print(e)
				elif p["in"] == "query":
					if query == "":
						query = "?"
					else:
						query += "&"
					query += p["name"] + "=" + str(paramValue)
				elif p["in"] == "formData":
					headers = {'Content-Type': "application/x-www-form-urlencoded", 'Accept': "application/json"}
					if formBodyData == None:
						formBodyData = ""
					else:
						formBodyData += "&"
					formBodyData += p["name"] + "=" + str(paramValue)
				i += 1
			url = url + query
			if jsonData:
				print(f"With Data {jsonData}")
			if formBodyData:
				print(f"With Form Data {formBodyData}")
			print("To: " + url)
			result = requests.request(method, url, json=jsonData, data=formBodyData, headers=headers)
			print(f"Result: {result.status_code} {result.text}")
			return {"result" : result.json(), "resultStatus" : result.status_code}
		except Exception as e:
			print(e)
			return {"result" : "", "resultStatus" : -1}

	def asyncRequest(self, method, spCallback, endpoint, *args):
		future = self.threadPool.submit(self.request, method, endpoint, *args)
		def callback(future):
			spCallback(future.result())
		future.add_done_callback(callback)

	def acGet(self, spCallback, endpoint, *args):
		self.asyncRequest("get", spCallback, endpoint, *args)

	def acPost(self, spCallback, endpoint, *args):
		self.asyncRequest("post", spCallback, endpoint, *args)

	def acPut(self, spCallback, endpoint, *args):
		self.asyncRequest("put", spCallback, endpoint, *args)

	def acDelete(self, spCallback, endpoint, *args):
		self.asyncRequest("delete", spCallback, endpoint, *args)

	def parseSwaggerFile(self, file):
		print("Parsing " + file)
		parser = SwaggerParser(swagger_path=file)
		self.spec = parser.specification

		scheme = "http"
		if len(self.spec.get("schemes", [])) > 0:
			scheme = self.spec["schemes"][0]
		if self.spec.get("host"):
			self.host.value = scheme + "://" + self.spec["host"]
		if self.spec.get("basePath"):
			self.basePath.value = self.spec["basePath"]

		self.clearActions()

		paths = self.spec['paths']
		for p in paths:
			methods = paths[p].keys()
			print(f"{'|'.join(methods).upper()} {self.basePath.value}{p}")
			for method in methods:

				details = paths[p][method]
				func = None
				if method == "get":
					func = self.acGet
				elif method == "post":
					func = self.acPost
				elif method == "put":
					func = self.acPut
				elif method == "delete":
					func = self.acDelete

				if func:
					action = self.addAsyncAction(method.upper() + " " + details["summary"], details["operationId"], func)
					action.addScriptTokens(["result", "resultStatus"])
					action.addStringParameter("endpoint", p)
					for param in details.get("parameters", []):
						parameterName = param["name"]
						parameterType = param.get("type", "")
						if parameterType in ["int", "integer", "int32", "int64", "byte"]:
							action.addIntParameter(parameterName, 0)
						elif parameterType in ["double", "float", "number"] :
							action.addFloatParameter(parameterName, 0.0)
						elif parameterType == "boolean":
							action.addBoolParameter(parameterName, 0.0)
						elif parameterType == "file":
							action.addFileParameter(parameterName, "")
						else:
							action.addStringParameter(parameterName, "")


if __name__ == "__main__":
	sp.registerPlugin(OpenAPIModule)
