import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dependencies"))

import sp
import json
import openapi_parser
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
		self.v2 = True
		sp.BaseModule.__init__(self)
		
	def afterInit(self):

		self.host = self.moduleContainer.addStringParameter("Host", "")
		self.basePath = self.moduleContainer.addStringParameter("Base Path", "")
		self.swaggerFile = self.moduleContainer.addFileParameter("Swagger File", "swagger.json")
		self.parse = self.moduleContainer.addTrigger("Parse")
		
	def onParameterFeedback(self, parameter):
		if parameter == self.swaggerFile or parameter == self.parse:
			self.parseFile(self.swaggerFile.value)

	def getUrl(self, endpoint):
		return self.host.value + self.basePath.value + endpoint
			
	def request(self, method, endpoint, *args):
		try:
			url = self.getUrl(endpoint)
			print(f"Sending request: {method} {args}")

			if self.v2:
				spec = self.spec['paths'][endpoint][method]
				parameters = spec.get("parameters", [])
			else:
				spec = self.specCache[endpoint][method]
				parameters = spec.parameters
			jsonData = None
			formBodyData = None
			query = ""
			headers = {'Content-Type': "application/json", 'Accept': "application/json"}
			i = 0
			for p in parameters:
				paramValue = args[i]
				if self.v2:
					paramName = p["name"]
					paramLocation = p["in"]
				else:
					paramName = p.name
					paramLocation = p.location.value

				if paramLocation == "path":
					url = url.replace("{"+paramName+"}", str(paramValue))
				elif paramLocation == "body":
					try:
						jsonData = json.loads(paramValue)
					except Exception as e:
						print(e)
				elif paramLocation == "query":
					if query == "":
						query = "?"
					else:
						query += "&"
					query += paramName + "=" + str(paramValue)
				elif paramLocation == "formData":
					headers = {'Content-Type': "application/x-www-form-urlencoded", 'Accept': "application/json"}
					if formBodyData == None:
						formBodyData = ""
					else:
						formBodyData += "&"
					formBodyData += paramName + "=" + str(paramValue)
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

	def parseSwaggerV2File(self, file):
		print("Parsing v2 " + file)
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
					operationId = details.get("operationId", None)
					if not operationId:
						operationId = details["summary"]
					action = self.addAsyncAction(method.upper() + " " + details["summary"], operationId, func)
					action.addScriptTokens(["result", "resultStatus"])
					action.addStringParameter("endpoint", p)
					for param in details.get("parameters", []):
						self.addActionParameter(action, param["name"], param.get("type", ""))

	def parseOpenAPIV3File(self, file):
		print("Parsing v3 " + file)
		try:
			self.spec = openapi_parser.parse(file)
		except:
			return False
		self.specCache = {}

		#scheme = "http"
		#nothing like that in v3?
		#if len(self.spec.get("schemes", [])) > 0:
		#	scheme = self.spec["schemes"][0]
		#if self.spec.get("host"):
		#	self.host.value = scheme + "://" + self.spec["host"]
		if len(self.spec.servers) > 0:
			self.basePath.value = self.spec.servers[0].url

		self.clearActions()

		for p in self.spec.paths:
			methods = [m.method.value for m in p.operations]
			print(f"{'|'.join(methods).upper()} {self.basePath.value}{p.url}")
			self.specCache[p.url] = {}

			for details in p.operations:
				self.specCache[p.url][details.method.value] = details
				func = None
				if details.method.value == "get":
					func = self.acGet
				elif details.method.value == "post":
					func = self.acPost
				elif details.method.value == "put":
					func = self.acPut
				elif details.method.value == "delete":
					func = self.acDelete

				if func:
					operationId = details.operation_id
					if not operationId:
						operationId = details.summary
					action = self.addAsyncAction(details.method.name + " " + details.summary, operationId, func)
					action.addScriptTokens(["result", "resultStatus"])
					action.addStringParameter("endpoint", p.url)
					for param in details.parameters:
						self.addActionParameter(action, param.name, param.schema.type.value)
		return True

	def addActionParameter(self, action, parameterName, parameterType):
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

	def parseFile(self, file):
		if self.parseOpenAPIV3File(file):
			self.v2 = False
		else:
			print("might be no v3 file, trying v2")
			self.parseSwaggerV2File(file)
			self.v2 = True

if __name__ == "__main__":
	sp.registerPlugin(OpenAPIModule)
