<?xml version="1.0" ?>
<?python
import time
def ymd(stamp):
    return time.strftime('%Y-%m-%d', time.localtime(int(stamp)))
    
?>
<div xmlns:py="http://purl.org/kid/ns#">
	<p>
		<strong>Package:</strong> <span py:replace="pkg_data['name']"/><br/>
		<strong>Summary:</strong> <span py:replace="pkg_data['summary']"/>
	</p>
	<p>
		<strong>Description:</strong><br/>
		<span py:replace="pkg_data['description']"/>
	</p>
	<h3>Changes:</h3>
	<table border="0" cellpadding="0" cellspacing="5">
        <tr py:for="(e, v, r, a, built, size, loc, author, log, added) in pkg_data['rpms']">
            <td valign="top"><a href="${'%s/%s' % (url, loc)}" 
              py:content="'%s-%s-%s.%s' % (pkg_data['name'], v, r, a)"/>
              [<span style="white-space: nowrap" py:content="size"/>]</td>
            <td valign="top">
              <strong>Changelog</strong>
              by <span py:content="'%s (%s)' % (author, ymd(added))"/>:
              <pre style="margin: 0pt 0pt 5pt 5pt" py:content="log"/>
            </td>
        </tr>
    </table>
</div>
