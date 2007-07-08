<?xml version="1.0" encoding="utf-8"?>
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title py:content="'RepoView: %s' % repo_data['title']"/>
  <link rel="stylesheet" href="layout/repostyle.css" type="text/css"/>
</head>
<body>
    <div class="levbar">
      <p class="pagetitle" py:content="group_data['name']"/>
      <ul class="levbarlist">
        <li>
        <a href="${group_data['filename']}" 
        	title="Back to package listing"
        	class="nlink">&laquo; Back to all packages</a>
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
        <h2 py:content="'%s - %s' % (pkg_data['name'], pkg_data['summary'])"/>
        <table cellpadding="3" cellspacing="0" width="100%">
        <tr>
            <th class="field">URL:</th><td><a href="${pkg_data['url']}" 
		py:content="pkg_data['url']"/></td>
	</tr>
	<tr>
	    <th class="field">License:</th><td py:content="pkg_data['rpm_license']"/>
        </tr>
        </table>
        <dl>
        <dt>Description:</dt>
        <dd><pre py:content="pkg_data['description']"/></dd>
        </dl>

        <h3>Packages</h3>
        <table cellpadding="3" cellspacing="3" width="100%">
            <tr>
                <th>Type</th>
                <th>Epoch:Version-Release</th>
		<th>Built</th>
                <th>Size</th>
		<th>Link</th>
            </tr>
            <tr py:for="(e, v, r, a, built, size, loc, log, author, added) in pkg_data['rpms']">
                
                <td py:content="'%s.%s' % (pkg_data['name'], a)"/>
                <td py:content="'%s:%s-%s' % (e, v, r)"/>
		<td py:content="built"/>
		<td py:content="size"/>
		<td>
                  <a href="${'../%s' % loc}" class="inpage">download</a>
                </td>
            </tr>
        </table>
        <!--h3>Changelog</h3>
        <dl py:for="log in pkglist[0].getChangeLogs()">
            <dt py:content="'* ' + log[0] + ' ' + log[1]"/>
            <dd><pre py:content="log[2]"/></dd>
        </dl-->
        <p class="footernote">
          Listing created by
          <a href="http://linux.duke.edu/projects/mini/repoview/"
            class="repoview" py:content="'Repoview-%s' % repo_data['my_version']"/>
        </p>
    </div>
</body>
</html>
