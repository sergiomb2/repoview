<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://naeblis.cx/ns/kid#">
<head>
  <title>RepoView</title>
  <link rel="stylesheet" href="{mkLinkUrl('layout/repostyle.css', isindex=1)}" type="text/css" />
</head>
<body>
    <div class="levbar">
    <p class="pagetitle">Available Groups</p>
    <ul class="levbarlist">
      <li py:for="grp in groups.getSortedList()">
        <a class="nlink"
            href="{mkLinkUrl(grp, isindex=1)}"
            title="{grp.name}"
            py:content="len(grp.grid) > 20 and '%s...' % grp.grid[:17] or grp.grid"/>
      </li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in letters.getSortedList()"
              class="nlink"
              href="{mkLinkUrl(letter, isindex=1)}" py:content="letter.grid"/>
          </span>]
        </p>
        <h2>RepoView</h2>
        <ul class="pkglist">
          <li>
            Total Packages: 
            <span py:content="pkgcount"/>
            <span py:if="pkgignored">
              (<span py:content="pkgignored"/> ignored:
              <span py:content="', '.join(ignore)"/>)
            </span>
          </li>
          <li>
            Available Architectures: 
            <span py:content="', '.join(arches)"/>
            <span py:if="len(xarch)">
              (<span py:content="len(xarch)"/> ignored:
              <span py:content="', '.join(xarch)"/>)
            </span>
          </li>
          <li>
            Total groups: <span py:content="len(groups.keys())"/>
          </li>
        </ul>
        <h3>Latest packages:</h3>
        <ul class="pkglist">
          <li py:for="pkg in groups['__latest__'].getSortedList(trim=0)">
            <a href="{mkLinkUrl(pkg, isindex=1)}" class="inpage"
                py:content="'%s-%s-%s' % (pkg.n, pkg.v, pkg.r)"/>:
            <span py:content="pkg.summary"/>
          </li>
        </ul>
        <h3>Available Groups</h3>
        <ul class="pkglist">
          <li py:for="grp in groups.getSortedList()">
            <a href="{mkLinkUrl(grp, isindex=1)}" class="inpage"
                py:content="grp.name"/>
          </li>
        </ul>
        <p class="footernote" py:content="'Listing generated: %s' % gentime"/>
    </div>
</body>
</html>
