<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title>RepoView</title>
  <link rel="stylesheet" href="${mkLinkUrl('layout/repostyle.css')}" type="text/css" />
</head>
<body>
    <div class="levbar">
    <p class="pagetitle">
        <a href="${mkLinkUrl('index.html')}" 
        title="Back to the index page"
        class="nlink">Available Groups</a>
    </p>
    <ul class="levbarlist">
      <li py:for="grp in groups.getSortedList()">
        <a class="${grp.name == group.name and 'nactive' or 'nlink'}"
            href="${mkLinkUrl(grp)}"
            title="${grp.name}"
            py:content="len(grp.grid) > 20 and '%s...' % grp.grid[:17] or grp.grid"/>
      </li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in letters.getSortedList()"
              class="nlink"
              href="${mkLinkUrl(letter)}" py:content="letter.grid"/>
          </span>]
        </p>
        <h2 py:content="group.name"/>
        <ul class="pkglist">
          <li py:for="pkg in group.getSortedList(trim=0)">
            <a href="${mkLinkUrl(pkg)}" class="inpage"
                py:content="'%s-%s-%s' % (pkg.n, pkg.v, pkg.r)"/>:
            <span py:content="pkg.summary"/>
          </li>
        </ul>
        <p class="footernote">
          <span py:content="'Listing generated: %s by' % gentime"/>
          <a href="http://linux.duke.edu/projects/mini/repoview/"
            class="repoview" py:content="'RepoView-%s' % VERSION"/>
        </p>
    </div>
</body>
</html>
