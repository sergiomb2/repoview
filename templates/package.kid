<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title py:content="'RepoView: %s' % stats['title']"/>
  <link rel="stylesheet" href="${mkLinkUrl('layout/repostyle.css')}" type="text/css"/>
</head>
<body>
    <div class="levbar">
      <p class="pagetitle">
        <a href="${mkLinkUrl(pkglist[0].group)}"
            class="nlink"
            py:content="pkglist[0].group.name"/>
      </p>
      <ul class="levbarlist">
        <li py:for="pkg in pkglist[0].group.getSortedList(trim=20,name=pkglist[0].n)">
         <a class="${pkg.n == pkglist[0].n and 'nactive' or 'nlink'}"
            href="${mkLinkUrl(pkg)}"
            title="${'%s' % pkg.summary}"
            py:content="len(pkg.n) > 20 and '%s...' % pkg.n[:17] or pkg.n"/>
      </li>
    </ul>

    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in letters.getSortedList()"
              class="${pkglist[0].n[0].upper() == letter.grid and 'nactive' or 'nlink'}"
              href="${mkLinkUrl(letter)}" py:content="letter.grid"/>
          </span>]
        </p>
        <h2 py:content="'%s - %s' % (pkglist[0].n, pkglist[0].summary)"/>
        <dl>
        <dd><pre py:content="pkglist[0].description"/></dd>
        </dl>
        <table cellpadding="3" cellspacing="0" width="100%">
        <tr>
            <th class="field">License:</th><td py:content="pkglist[0].license"/>
            <th class="field">Group:</th><td py:content="pkglist[0].group or pkglist[0].rpmgroup"/>
        </tr>
        <tr>
            <th class="field">URL:</th><td><a href="${pkglist[0].url}" class="inpage" py:content="pkglist[0].url"/></td>
            <th py:if="pkglist[0].sourcename" class="field">Source:</th>
                <td py:if="pkglist[0].sourcename"><a py:if="pkglist[0].sourceurl" py:content="pkglist[0].sourcename" href="${mkLinkUrl(pkglist[0].sourceurl)}" class="inpage"/><span py:if="not pkglist[0].sourceurl" py:content="pkglist[0].sourcename"/>
                </td>
        </tr>
        </table>
        <h3>Packages</h3>
        <table cellpadding="3" cellspacing="3" width="100%">
            <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Release</th>
                <th>Type</th>
                <th>Size</th>
                <th>Built</th>
            </tr>
            <tr py:for="pkg in pkglist">
                <td><a href="${mkLinkUrl(pkg.getFileName())}" class="inpage" py:content="pkg.n"/></td>
                <td py:content="pkg.v"/>
                <td py:content="pkg.r"/>
                <td py:content="pkg.arch"/>
                <td py:content="pkg.getSize()"/>
                <td py:content="pkg.getTime()"/>
            </tr>
        </table>
        <h3>Changelog</h3>
        <dl py:for="log in pkglist[0].getChangeLogs()">
            <dt py:content="'* ' + log[0] + ' ' + log[1]"/>
            <dd><pre py:content="log[2]"/></dd>
        </dl>
        <p class="footernote">
          Listing created by
          <a href="http://linux.duke.edu/projects/mini/repoview/"
            class="repoview" py:content="'RepoView-%s' % stats['VERSION']"/>
        </p>
    </div>
</body>
</html>
