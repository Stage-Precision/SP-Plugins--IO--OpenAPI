import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dependencies"))

import sp
from swagger_parser import SwaggerParser
import requests

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
	
	def acGet(self, endpoint, *args):
		print(endpoint)
		print(args)
		url = self.getUrl(endpoint)

		spec = self.spec['paths'][endpoint]['get']
		i = 0
		for p in spec["parameters"]:
			paramValue = args[i]
			if p["in"] == "path":
				url = url.replace("{"+p["name"]+"}", str(paramValue))
			i += 1
		print(url)
		result = requests.get(url)
		print(result.status_code, result.text)
		return {"result" : result.json(), "resultStatus" : result.status_code}

	def acPost(self, endpoint, *args):
		print(endpoint)
		print(args)

	def acPut(self, endpoint, *args):
		print(endpoint)
		print(args)

	def acDelete(self, endpoint, *args):
		print(endpoint)
		print(args)

	def parseFile(self, file):
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
					action = self.addAction(method.upper() + " " + details["summary"], details["operationId"], func)
					action.addScriptTokens(["result", "resultStatus"])
					action.addStringParameter("endpoint", p)
					for param in details.get("parameters", []):
						parameterName = param["name"]
						parameterType = param.get("type")
						if parameterType == "integer":
							action.addIntParameter(parameterName, 0)
						else:
							action.addStringParameter(parameterName, str(parameterType))


if __name__ == "__main__":
	sp.registerPlugin(OpenAPIModule)
