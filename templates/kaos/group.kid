<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title py:content="'RepoView KAOS: %s' % repo_data['title']"/>
  <meta charset="utf-8" />
  <link rel="stylesheet" href="layout/repostyle.css" type="text/css" />
  <meta name="robots" content="noindex,follow" />
  <meta property="og:site_name" content="${repo_data['title']}" />
  <meta property="og:title" content="${group_data['name']}" />
  <meta property="og:description" content="Packages in group ${group_data['name']}" />
</head>
<body>
    <div class="levbar">
    <p class="page-title" py:content="group_data['name']"/>
    <ul class="levbar-list">
  <li>
        <a href="index.html" 
          title="Back to the index page"
          class="nlink">← Back to index</a>
  </li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letter-list">
            <a py:for="letter in repo_data['letters']"
              class="nlink"
              href="${'letter_%s.group.html' % letter.lower()}" py:content="letter"/>
          </span>]
        </p>
        <h2 py:content="group_data['name']"/>
  <p py:content="group_data['description']"/>
        <ul class="pkg-list">
          <li py:for="(name, filename, summary) in group_data['packages']">
            <a href="${filename}" class="inpage" py:content="name"/> - 
            <span py:content="summary"/>
          </li>
        </ul>
        <p class="footer-note">
          Listing created by
          <a href="https://github.com/essentialkaos/repoview-kaos"
            class="repoview" py:content="'repoview-kaos-%s' % repo_data['my_version']"/>
        </p>
    </div>
</body>
</html>
