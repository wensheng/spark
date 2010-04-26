r"""
Sprite - Spark's Python Ruby Implementation of Template Engine
Copyright (c) 2005 Wensheng Wang
License: MIT
contributors:
	Ian Meyer: suggestion and patch of conditional
"""

import os, sys, re

class Sprite:
	"""A simple python template engine:
	It take a text template file as input, process the tags and blocks in 
	the file, and return the resulted text.  It will compile the input
	into a python program and store it in the cache location if the template is
	newer. On the next request of displaying the same file, it will not read the
	text file, instead it will execute the cached python program.
	In the template file: tags are enclosed by '${}' and blocks are denoted
	in html comment in the form of '<!-- BEGIN block_name -->' and '<!-- END -->'.
	Users use set_vars and set_block to specify the value of tag and block
	variables inside their python program.

	Note the BEGIN and END block will take whole line, anything else on the same 
	line will be ignored.
	"""

	def __init__ (self, filename, template_dir='.', cache_dir='.'):
		self.update(filename, template_dir, cache_dir)
		#self.cache_dir = cache_dir
		#if filename.startswith('/'): self.template_file = filename
		#else: self.template_file = os.path.join(template_dir,filename)
		#self.cache_module = re.sub("[\/\\\.: ]",'_',os.path.realpath(self.template_file))
		#self.cache_file = os.path.join(cache_dir,self.cache_module) + '.py'
		self.tpldata={}
		self.tplscope={}
		self.if_dep=1
		self.tab_dep=1
		self.page=[]
		self.errors = ['']
		
	def update(self, filename, template_dir, cache_dir):
		"""Update the engine with a different template. 
		"""
		self.cache_dir = cache_dir
		if filename.startswith('/'): self.template_file = filename
		else: self.template_file = os.path.join(template_dir,filename)
		self.cache_module = re.sub("[\/\\\.: ]",'_',os.path.realpath(self.template_file))
		self.cache_file = os.path.join(cache_dir,self.cache_module) + '.py'

	def refresh(self, filename, template_dir, cache_dir):
		"""use new template and discard previous template
		"""
		self.update(filename, template_dir, cache_dir)
		self.tab_dep=1
		self.page=[]

	def set_vars(self,dictvar):
		"update top-level var from an dict"
		if type(dictvar) == type({}):
			self.tpldata.update(dictvar)
		else:
			self.errors.append('Error in "set_vars(%s)", set_vars accepts only dict'%dictvar)

	def set_block(self, blockname, bdict={}):
		"Assign key value pairs from an dict to a specified block "
		if not type(bdict) == type({}):
			self.errors.append('Error in "set_block(%s)", last argument must be dict'%bdict)
			return

		blocks = blockname.split('.')
		
		#if not self.tpldata.has_key(blocks[0]):
		if blocks[0] not in self.tpldata:
			self.tpldata[blocks[0]] = []
		curr = self.tpldata[blocks[0]]

		for block in blocks[1:]:
			if not curr:
				curr.append({})
			curr = curr[-1]
			if block not in curr:
				curr[block] = []
			curr = curr[block]
    	
		curr.append(dict(bdict))
	
	def display(self, no_cache=0):
		"""Display: 
		If the template is newer, load the template, 
		compile it to cache python code and display the output,
		Otherwise execute the cached python code. 
		"""
		if not no_cache and ( os.path.isfile(self.cache_file) \
		 and (os.path.getmtime(self.cache_file) >= os.path.getmtime(self.template_file) ) ):
			sys.path.append(self.cache_dir)
			cached=__import__(self.cache_module)
			self.page+= cached.displayself(self.tpldata)
		else:
			fp = open(self.template_file, 'r')
			self.compiled_code = self._compile(fp)
			fp.close()

			if not no_cache:
				fp = open(self.cache_file, 'w')
				fp.write (self.compiled_code)
				fp.close()
				os.chmod(self.cache_file, 0644)

			exec self.compiled_code
			self.page+= displayself(self.tpldata)
		self.page+= self.errors
		#2/13/06 will return list of string from now on
		#return "\n".join(self.page)
		return self.page

	def _find_block(self, textline):
		m = re.match(r".*<!--\s*BEGIN\s+((\w+\.)*\w+)\s+-->",textline)
		if m: return [1,m.groups()[0]]
		m = re.match(r".*<!--\s*END\s+(((\w+\.)*\w+)\s+)*-->",textline)
		if m: return [2,m.groups()[1]]
		return [0]

	def _find_conditional(self, textline):
		"""Find IF, ELIF, ELSE, ENDIF"""
		#should we provide 'AND' 'OR'?
		cond_beg = textline[textline.find('<!--')+4:].lstrip()
		cond_end = cond_beg.find('-->')

		if cond_end == -1:
			return [0]
		if cond_beg[:2] == "IF":
			return [1,cond_beg[2:cond_end].lstrip().rstrip()]
		elif cond_beg[:4] == "ELIF":
			return [2,cond_beg[4:cond_end].lstrip().rstrip()]
		elif cond_beg[:4] == "ELSE":
			return [3]
		elif cond_beg[:5] == "ENDIF":
			return [4]
		else:
			return [0]

	def _find_tags(self, textline):
		"""This is to replace following regular expression:
		re.compile("\${[a-zA-Z0-9_\-\.]+\}")
		"""
		tags = []
		remain = textline
		while remain:
			tagb = remain.find('${')
			tage = remain.find('}')
			if not tagb == -1 and tagb < tage:
				tags.append(remain[tagb:tage+1])
				remain=remain[tage+1:]
			else:
				remain = ''
		return tags

	def _compile_var_tags(self, text_line):
		"Find and replace tags and blocks variables"
		curr_line = text_line
		
	        #---------------------------------------------------------
		# Find conditionals
		var = self._find_conditional(curr_line)
		if var[0]:
			if var[0] == 1 or var[0] == 2:
				var_length = var[1].find(' ')
				if var_length == -1:
					cond = ''
					var_to_test = var[1]
				else:
					var_to_test = var[1][:var_length]
					#has EQ ,NE, LT, or GT
					rest_of_conditional = var[1][var_length:].lstrip()
					cond = rest_of_conditional.find(' ')
					if cond == -1:
						self.error_found = 1
						return '\t'*self.tab_dep+'pass\n\tappend("Template Error:Wrong conditional syntax at line ' + str(self.lineno) + '")'
					else:
						value_to_test = rest_of_conditional[cond:].lstrip()
						cond = rest_of_conditional[:cond]

				var_to_test = self._get_varname(var_to_test)
				if not var_to_test:
					self.error_found = 1
					return '\t'*self.tab_dep+'pass\n\tappend("Template Error:Not in this block :'+ v + " at line " + str(self.lineno) + '")'

				if not cond:
					condition = var_to_test + ":"
				elif cond == "EQ":
					#can be numeric or string, string must be quoted
					condition = var_to_test + " == " + value_to_test + ":"
				elif cond == "NE":
					condition = var_to_test + " != " + value_to_test + ":"
				elif cond == "LT":
					condition = var_to_test + " < " + value_to_test + ":"
				elif cond == "GT":
					condition = var_to_test + " and " + var_to_test + " > " + value_to_test + ":"
				else:
					self.error_found = 1
					return '\t'*self.tab_dep+'pass\n\tappend("Template Error:Not in this block :'+ v + " at line " + str(self.lineno) + '")'

				if var[0] == 1:
					curr_line =  "\t" * self.tab_dep + "if " + condition
					self.if_dep +=1
				else:
					if self.if_dep == 0:
						self.error_found = 1
						return '\t'*self.tab_dep+'pass\n\tappend("Template Error:ELIF has no matching IF at line ' + str(self.lineno) + '")'
					self.tab_dep -= 1
					curr_line =  "\t" * self.tab_dep + "elif " + condition
				self.tab_dep = self.tab_dep + 1
			elif var[0] == 3:
				if self.if_dep == 0:
					self.error_found = 1
					return '\t'*self.tab_dep+'pass\n\tappend("Template Error:ELSE has no matching IF at line ' + str(self.lineno) + '")'
				self.tab_dep = self.tab_dep - 1
				curr_line = "\t" * self.tab_dep + "else:"
				self.tab_dep = self.tab_dep + 1
			elif var[0] == 4:
				if self.if_dep == 0:
					self.error_found = 1
					return '\t'*self.tab_dep+'pass\n\tappend("Template Error:ENDIF has no matching IF at line ' + str(self.lineno) + '")'
				self.tab_dep = self.tab_dep - 1
				self.if_dep -= 1
				if not self.tab_dep:
					self.error_found = 1
					self.tab_dep = 1
					return '\tappend("Template Error: ENDIF has No matching IF at line %d")' % self.lineno
				curr_line = ''
			return curr_line

		mstr = self._find_block(curr_line)
		if mstr[0]:
			if mstr[0] == 1: 
				#--------------------------------
				# match <!-- BEGIN var --> block
				curr_line = ''
				blocks = mstr[1].split('.')
				curr_scope = self.tplscope
				if len(blocks)==1:
					dictname = "tpldata"
				else:
					for b in blocks[:-1]:
						if b not in curr_scope:
							return '\tappend("Template Error: No such parent block: %s at line %d")' % (b,self.lineno)
						curr_scope = curr_scope[b]
					dictname = "item_"+blocks[-2]
				curr_scope[blocks[-1]]={}

				curr_line = "\t" * self.tab_dep + "for item_" + blocks[-1] + " in " + dictname + ".get('" + blocks[-1] +"',[]):"
				self.tab_dep += 1
					
				return curr_line
			elif mstr[0] == 2:
				#-----------------------------
				# match <!-- END var --> block
				self.tab_dep -= 1
				if not self.tab_dep:
					self.error_found = 1
					self.tab_dep = 1
					return '\tappend("Template Error: END has No matching BEGIN at line %d")' % self.lineno
				return ""

		mstrs = self._find_tags(curr_line)
		if mstrs:
			#to solve '%' problem
			# "%d" will return "%d"
			# "%%d" % 3 will error
			# I can just print "%3" if 3 is not filled
			# if I want to print "%3" where 3 was filled
			# I have to use "%%%d" % 3
			curr_line=curr_line.replace('%','%%')

		varname=''
		#---------------------------------------------------------
		# match ${var} variable
		for mstr in mstrs:
			if varname:
				varname+=','
			varrefs = mstr.lstrip('${').rstrip('}').split('.')
	
			if len(varrefs)<2:
				#top level var
				varname += "tpldata.get('" + varrefs[0] + "','')"
			else:
				curr_scope = self.tplscope
				for v in varrefs[:-1]:
					if v not in curr_scope:
						self.error_found = 1
						return '\t'*self.tab_dep+'pass\n\tappend("Template Error:Not in this block :'+ v + " at line " + str(self.lineno) + '")'
					curr_scope = curr_scope[v]
				varname += "item_" + v + ".get('" + varrefs[-1] + "','')"

			curr_line = curr_line.replace(mstr, '%s')
		if mstrs:
			curr_line+="' %("+varname+"))"
		else:
			curr_line+="')"

		return curr_line

	def _get_varname(self,mstr):
		varrefs = mstr.lstrip('${').rstrip('}').split('.')
		if len(varrefs)<2:
			#top level var
			varname = "tpldata.get('" + varrefs[0] + "','')"
		else:
			curr_scope = self.tplscope
			for v in varrefs[:-1]:
				if v not in curr_scope:
					self.error_found = 1
					self.errors.append('Template Error:Not in this block :'+ v + " at line " + str(self.lineno))
					return ''
				curr_scope = curr_scope[v]
			varname = "item_" + v + ".get('" + varrefs[-1] + "','')"
		return varname
		
	def _compile(self,datafile):
		"""process the read-in data.
		"""
		template_py = 'def displayself(tpldata):\n';
		template_py += '\tpage=[]\n';
		template_py += '\tappend=page.append\n';
		self.lineno = 1
		self.error_found = 0
		for line in datafile:
			if self.error_found:
				break
			else:
				line=line.rstrip()
				#escape special chars
				line=line.replace("\\","\\\\").replace("'","\\'")
				tline = '\t'*self.tab_dep + "append('" + line
				template_py = template_py + self._compile_var_tags(tline)+'\n'
				self.lineno += 1
			
		template_py = template_py + '\treturn page\n'
		return  template_py


if __name__ == '__main__':
	def test():
		import time
		if not os.path.exists("testspark.txt"):
			f = open("testspark.txt",'w')
			f.write("""
<!-- BEGIN row -->
${row.num}
<!-- END -->
Time now is ${curtime}""")
			f.close()
			time.sleep(0.1)
		t=Sprite("testspark.txt")
		t.set_vars({'curtime':time.ctime()})
		t.set_vars({'hi':1})
		for i in range(100):
			t.set_block('row',{'num':i})
		print " ".join(t.display())
	test()
