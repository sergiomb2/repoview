<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://naeblis.cx/ns/kid#">
<head>
  <title>RepoView</title>
  <link rel="stylesheet" href="{mkLinkUrl('layout/repostyle.css')}" type="text/css" />
</head>
<body>
    <div class="levbar">
    <p class="pagetitle">
        <a href="{mkLinkUrl(package.group)}"
            class="nlink"
            py:content="package.group.name"/>
    </p>
    <ul class="levbarlist">
      <li py:for="pkg in package.group.getSortedList(trim=20, nevr=package.nevr)">
         <a class="{pkg.nevr == package.nevr and 'nactive' or 'nlink'}"
            href="{mkLinkUrl(pkg)}"
            title="{'%s-%s-%s: %s' % (pkg.n, pkg.v, pkg.r, pkg.summary)}"
            py:content="len(pkg.n) > 20 and '%s...' % pkg.n[:17] or pkg.n"/>
      </li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in letters.getSortedList()"
              class="{package.n[0].upper() == letter.grid and 'nactive' or 'nlink'}"
              href="{mkLinkUrl(letter)}" py:content="letter.grid"/>
          </span>]
        </p>
        <h2 py:content="'%s: %s' % (package.n, package.summary)"/>
        <table cellpadding="3" cellspacing="0" width="100%">
        <tr>
            <th>Name:</th><td py:content="package.n"/>
            <th>Vendor:</th><td py:content="package.vendor"/>
        </tr>
        <tr>
            <th>Version:</th><td py:content="package.v"/>
            <th>License:</th><td py:content="package.license"/>
        </tr>
        <tr>
            <th>Release:</th><td py:content="package.r"/>
            <th>URL:</th><td><a href="{package.url}" class="inpage"><span py:content="package.url"/></a></td>
        </tr>
        </table>
        <dl>
        <dt>Summary</dt>
        <dd py:content="package.description"/>
        </dl>
        <div py:for="arch in package.arches.values()">
            <h3 py:content="'Arch: ' + arch.arch"/>
            <table cellpadding="3" cellspacing="0" width="100%">
                <tr><th>Download:</th><td><a href="{mkLinkUrl(arch)}" class="inpage" py:content="arch.getFileName()"/></td></tr>
                <tr><th>Build Date:</th><td py:content="arch.getTime()"/></tr>
                <tr><th>Packager:</th><td py:content="arch.packager"/></tr>
                <tr><th>Size:</th><td py:content="arch.getSize()"/></tr>
            </table>
        </div>
        <h2>Changelog</h2>
        <dl py:for="log in package.getChangeLogs()">
            <dt py:content="'* ' + log[0] + ' ' + log[1]"/>
            <dd><pre py:content="log[2]"/></dd>
        </dl>
        <p class="footernote" py:content="'Listing generated: %s' % gentime"/>
    </div>
</body>
</html>
