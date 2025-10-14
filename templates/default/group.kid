<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://genshi.edgewall.org/">
<head>
  <title py:content="'RepoView: %s' % repo_data['title']"/>
  <link rel="stylesheet" href="layout/repostyle.css" type="text/css" />
  <meta name="robots" content="noindex,follow" />
</head>
<body>
    <div class="levbar">
    <p class="pagetitle" py:content="group_data['name']"/>
    <ul class="levbarlist">
	<li>
        <a href="index.html" 
        	title="Back to the index page"
        	class="nlink">&laquo; Back to index</a>
	</li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in repo_data['letters']"
              class="nlink"
              href="${'letter_%s.group.html' % letter.lower()}" py:content="letter"/>
          </span>]
        </p>
        <h2 py:content="group_data['name']"/>
	<p py:content="group_data['description']"/>
        <ul class="pkglist">
          <li py:for="(name, filename, summary) in group_data['packages']">
            <a href="${filename}" class="inpage" py:content="name"/> - 
            <span py:content="summary"/>
          </li>
        </ul>
        <p class="footernote">
          Listing created by
          <a href="https://github.com/sergiomb2/repoview/"
            class="repoview" py:content="'Repoview-%s' % repo_data['my_version']"/>
        </p>
    </div>
</body>
</html>
