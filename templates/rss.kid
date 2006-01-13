<?xml version="1.0" ?>
<div xmlns:py="http://purl.org/kid/ns#">
	<p>
		<strong>Package:</strong> <span py:replace="'%s-%s-%s' % (package.n, package.v, package.r)"/><br/>
		<strong>Summary:</strong> <span py:replace="package.summary"/>
	</p>
	<p>
		<strong>Description:</strong><br/>
		<span py:replace="package.description"/>
	</p>
	<h3>ChangeLog:</h3>
	<p>
		<span py:for="log in package.getChangeLogs()" py:strip=''>
			<strong py:content="'* ' + log[0] + ' ' + log[1]"/><br/>
			<pre py:content="log[2]"/><br/>
		</span>
	</p>
	<p>(<a href="${mkLinkUrl(package, isrss=1)}">More info</a>)</p>
</div>